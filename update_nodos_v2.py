"""Enrich nodos_v2.csv with the full article text from articulos_pot.json,
remove duplicates, and update kpi_pot.csv with corrected counts.

Changes applied:
  - For every row with `tipo == "articulo"`, replace `resumen` with the full
    article body and rewrite `etiqueta` as "Artículo N. <título>" (no truncation).
  - Drop the duplicate row n833 (Art. 355 — orphan, has no edges).
  - Drop the corrupt row n15 (label was "Articulo 412, Articulo 413 y Articulo 414"
    — a cross-reference parsed as an article). Rewire the single edge that
    pointed to it (from n768) to n767, the real Art. 412 node.
  - Update `parte`, `titulo_pot` and `capitulo_pot` from the canonical extraction
    when missing on the article row.
  - Recompute kpi_pot.csv (`total_nodos`, `total_articulos`, `total_relaciones`).
"""

import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent
ARTS = json.loads((REPO / "articulos_pot.json").read_text(encoding="utf-8"))
ART_BY_NUM = {a["numero"]: a for a in ARTS}

NODES_PATH = REPO / "nodos_v2.csv"
EDGES_PATH = REPO / "relaciones_v2.csv"
KPI_PATH = REPO / "kpi_pot.csv"

DROP_NODE_IDS = {"n833", "n15"}
EDGE_REWIRES = {"n15": "n767"}  # repoint cross-reference from corrupt 412 to real 412


def update_nodes():
    with NODES_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    out_rows = []
    article_count = 0
    enriched = 0
    for row in rows:
        if row["id"] in DROP_NODE_IDS:
            continue
        if row.get("tipo") == "articulo":
            article_count += 1
            try:
                num = int(row["numero"])
            except (ValueError, TypeError):
                num = None
            art = ART_BY_NUM.get(num)
            if art:
                titulo = art["titulo"].strip()
                row["etiqueta"] = f"Artículo {num}. {titulo}"
                row["resumen"] = art["texto"]
                # Backfill jerarchy if missing.
                if not row.get("parte") and art.get("parte"):
                    row["parte"] = art["parte"]
                if not row.get("titulo_pot") and art.get("titulo_pot"):
                    row["titulo_pot"] = art["titulo_pot"]
                if not row.get("capitulo_pot") and art.get("capitulo"):
                    row["capitulo_pot"] = art["capitulo"]
                enriched += 1
        out_rows.append(row)

    with NODES_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    print(f"Nodos: {len(rows)} → {len(out_rows)} (eliminados {len(rows)-len(out_rows)})")
    print(f"Filas tipo=articulo: {article_count} (enriquecidas con texto: {enriched})")
    return out_rows


def update_edges():
    with EDGES_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    out_rows = []
    rewired = 0
    dropped = 0
    for row in rows:
        o, d = row["origen_id"], row["destino_id"]
        if o in EDGE_REWIRES:
            row["origen_id"] = EDGE_REWIRES[o]
            rewired += 1
        if d in EDGE_REWIRES:
            row["destino_id"] = EDGE_REWIRES[d]
            rewired += 1
        # Drop edges that touch nodes we removed (and that aren't covered by rewire).
        if row["origen_id"] in DROP_NODE_IDS or row["destino_id"] in DROP_NODE_IDS:
            dropped += 1
            continue
        # Avoid self-loops introduced by rewire.
        if row["origen_id"] == row["destino_id"]:
            dropped += 1
            continue
        out_rows.append(row)

    with EDGES_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    print(f"Aristas: {len(rows)} → {len(out_rows)} (rewired={rewired}, dropped={dropped})")
    return out_rows


def update_kpi(nodes, edges):
    article_nums = set()
    titulos = capitulos = partes = definiciones = 0
    for r in nodes:
        if r.get("tipo") == "articulo":
            try:
                article_nums.add(int(r["numero"]))
            except (ValueError, TypeError):
                pass
            if r.get("es_definicion") == "1":
                definiciones += 1
        elif r.get("tipo") == "titulo":
            titulos += 1
        elif r.get("tipo") == "capitulo":
            capitulos += 1
        elif r.get("tipo") == "parte":
            partes += 1

    jerarq = sum(1 for e in edges if e.get("tipo") == "contiene")
    cross = sum(1 for e in edges if e.get("tipo") == "referencia_cruzada")

    temas = set()
    for r in nodes:
        for t in (r.get("tema") or "").split("|"):
            t = t.strip()
            if t:
                temas.add(t)

    kpis = [
        ("total_nodos", len(nodes), "Total de nodos únicos"),
        ("total_articulos", len(article_nums), "Artículos del POT"),
        ("total_titulos", titulos, "Títulos del POT"),
        ("total_capitulos", capitulos, "Capítulos del POT"),
        ("total_partes", partes, "Partes del POT"),
        ("total_definiciones", definiciones, "Definiciones formales identificadas"),
        ("total_relaciones", len(edges), "Total de relaciones"),
        ("relaciones_jerarquicas", jerarq, "Relaciones jerárquicas (contiene)"),
        ("referencias_cruzadas", cross, "Referencias cruzadas entre artículos"),
        ("total_temas", len(temas), "Ejes temáticos identificados"),
    ]

    with KPI_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metrica", "valor", "descripcion"])
        for k in kpis:
            w.writerow(k)

    print("\nkpi_pot.csv actualizado:")
    for k, v, _ in kpis:
        print(f"  {k} = {v}")


def main():
    print("Actualizando nodos_v2.csv ...")
    nodes = update_nodes()
    print("\nActualizando relaciones_v2.csv ...")
    edges = update_edges()
    print("\nRecomputando kpi_pot.csv ...")
    update_kpi(nodes, edges)
    print("\nListo.")


if __name__ == "__main__":
    main()
