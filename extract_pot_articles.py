"""Extract the 622 articles of Medellín's POT (Acuerdo 48 de 2014) from the source PDF.

Strategy: render `POT-Medellin (1).pdf` with `pdftotext -layout`, then walk the
text searching for articles in numerical order (1, 2, 3, …, 622). Because the
articles appear in increasing numerical order in the document, a sequential
search avoids confusion with inline references to articles by number.

Each article body is the text between its header line and the header line of
the next article (or end of document). Page headers/footers and recurring
running titles are removed.
"""

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PDF = REPO / "POT-Medellin (1).pdf"
TXT = REPO / ".pot_layout.txt"
OUT_JSON = REPO / "articulos_pot.json"
OUT_CSV = REPO / "articulos_pot.csv"


def render_text() -> str:
    if not TXT.exists():
        subprocess.run(["pdftotext", "-layout", str(PDF), str(TXT)], check=True)
    return TXT.read_text(encoding="utf-8")


# Recurring page header/footer fragments to strip from article bodies.
PAGE_NOISE = [
    re.compile(r"^\s*Acuerdo\s+48\s+DE\s+2014\s*$", re.IGNORECASE),
    re.compile(r"^\s*“?Por medio del cual se revisa y ajusta el Plan de Ordenamiento Territorial.*”?\s*$"),
    re.compile(r'^\s*"?Por medio del cual se revisa y ajusta el Plan de Ordenamiento Territorial.*"?\s*$'),
    re.compile(r"^\s*\d{1,4}\s*$"),  # bare page number
]

RE_PARTE = re.compile(r"^\s*PARTE\s+([IVXLC]+)\b\.?\s*(.*?)\s*$")
RE_TITULO = re.compile(r"^\s*T[IÍ]TULO\s+([IVXLC]+)\b\.?\s*(.*?)\s*$")
RE_CAPITULO = re.compile(r"^\s*CAP[IÍ]TULO\s+([IVXLC]+)\b\.?\s*(.*?)\s*$")
RE_SECCION = re.compile(r"^\s*SECCI[ÓO]N\s+([IVXLC0-9]+)\b\.?\s*(.*?)\s*$")


def is_noise(line: str) -> bool:
    return any(p.match(line) for p in PAGE_NOISE)


def header_match(line: str, n: int) -> "re.Match | None":
    """Match line as the header for article number `n`.

    Real headers start at column 0 (or with very small indent) with the form:
        Artículo N. Title...
    or
        Artículo N.    Title...
    Inline references inside paragraphs typically have leading whitespace OR
    are followed/preceded by additional "Artículo M" tokens on the same line.
    """
    pat = re.compile(rf"^\s{{0,8}}Art[íi]culo\s+{n}\s*[\.,]?\s+(.+?)\s*$")
    m = pat.match(line)
    if not m:
        return None
    rest = line.strip()
    # Reject if the same line names another article number → reference.
    others = re.findall(r"Art[íi]culo\s+(\d+)", rest)
    if len([x for x in others if int(x) != n]) > 0:
        return None
    return m


def normalize_body(lines: list[str]) -> str:
    """Drop page noise; collapse whitespace; dedent the layout-induced indent."""
    out: list[str] = []
    blank_run = 0
    for ln in lines:
        if is_noise(ln):
            continue
        ln = ln.rstrip()
        if not ln.strip():
            blank_run += 1
            if blank_run <= 1:
                out.append("")
            continue
        blank_run = 0
        out.append(ln)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    indents = [len(ln) - len(ln.lstrip(" ")) for ln in out if ln.strip()]
    common = min(indents) if indents else 0
    if common:
        out = [(ln[common:] if len(ln) >= common else ln) for ln in out]
    return "\n".join(out)


def extract():
    raw = render_text().split("\n")

    # Walk the text sequentially, finding article N starting from line `cursor`.
    # Track hierarchy markers along the way.
    parte = titulo = capitulo = seccion = ""
    headers = []  # (line_idx, num, title, parte, titulo, capitulo, seccion)

    cursor = 0
    for n in range(1, 623):
        # Look for the header of article n starting at cursor.
        found = -1
        title = ""
        for i in range(cursor, len(raw)):
            line = raw[i]
            stripped = line.strip()

            # Update hierarchy from uppercase heading lines.
            if stripped and stripped == stripped.upper() and len(stripped) > 4:
                if "ARTÍCULO" not in stripped and "ARTICULO" not in stripped:
                    if RE_PARTE.match(line):
                        parte = stripped
                        titulo = capitulo = seccion = ""
                    elif RE_TITULO.match(line):
                        titulo = stripped
                        capitulo = seccion = ""
                    elif RE_CAPITULO.match(line):
                        capitulo = stripped
                        seccion = ""
                    elif RE_SECCION.match(line):
                        seccion = stripped

            m = header_match(line, n)
            if m:
                found = i
                title = m.group(1).strip()
                break

        if found < 0:
            print(f"WARN: no header found for article {n} starting at line {cursor}")
            continue

        headers.append({
            "line": found,
            "numero": n,
            "titulo": title,
            "parte": parte,
            "titulo_pot": titulo,
            "capitulo": capitulo,
            "seccion": seccion,
        })
        cursor = found + 1

    # The articulado ends before the appendices (ANEXOS). Find the line where the
    # post-articulado "TABLA DE CONTENIDO" starts so we don't sweep all annexes
    # into article 622's body.
    end_of_articulado = len(raw)
    if headers:
        last_start = headers[-1]["line"]
        for i in range(last_start + 1, len(raw)):
            if "TABLA DE CONTENIDO" in raw[i]:
                end_of_articulado = i
                break

    # Build records by slicing between consecutive headers.
    records = []
    for idx, h in enumerate(headers):
        next_line = headers[idx + 1]["line"] if idx + 1 < len(headers) else end_of_articulado
        body_lines = raw[h["line"] + 1: next_line]
        titulo = h["titulo"]
        # Fold title-wrap lines into the title. The PDF often breaks long titles
        # across two lines; we recognize this when the parsed title doesn't end
        # with '.' and the first non-noise body line is short and ends with '.'.
        if not titulo.rstrip().endswith("."):
            # Find the first non-noise non-empty line.
            for i, ln in enumerate(body_lines):
                if is_noise(ln) or not ln.strip():
                    continue
                cont = ln.strip()
                if len(cont) <= 80 and cont.endswith("."):
                    titulo = (titulo.rstrip() + " " + cont).strip()
                    body_lines = body_lines[i + 1:]
                break
        body = normalize_body(body_lines)
        records.append({
            "numero": h["numero"],
            "titulo": titulo,
            "parte": h["parte"],
            "titulo_pot": h["titulo_pot"],
            "capitulo": h["capitulo"],
            "seccion": h["seccion"],
            "texto": body,
            "longitud": len(body),
        })

    # Validate.
    nums = [r["numero"] for r in records]
    expected = set(range(1, 623))
    missing = sorted(expected - set(nums))
    extras = sorted(set(nums) - expected)
    dups = sorted({n for n in nums if nums.count(n) > 1})

    OUT_JSON.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["numero", "titulo", "parte", "titulo_pot", "capitulo", "seccion", "longitud", "texto"])
        for r in records:
            w.writerow([
                r["numero"], r["titulo"], r["parte"], r["titulo_pot"],
                r["capitulo"], r["seccion"], r["longitud"], r["texto"],
            ])

    print(f"Artículos extraídos: {len(records)}/622")
    print(f"Faltantes:    {missing if missing else 'ninguno'}")
    print(f"Duplicados:   {dups if dups else 'ninguno'}")
    print(f"Fuera de rango: {extras if extras else 'ninguno'}")
    short = [r["numero"] for r in records if r["longitud"] < 100]
    print(f"Cuerpos <100 chars (sospechosos): {short}")
    if records:
        avg = sum(r["longitud"] for r in records) / len(records)
        print(f"Longitud media: {avg:.0f} chars")
    print(f"\nSalidas:\n  {OUT_JSON.relative_to(REPO)}\n  {OUT_CSV.relative_to(REPO)}")

    if missing or dups or extras:
        sys.exit(1)


if __name__ == "__main__":
    extract()
