# Validación de la extracción de artículos del POT

**Fuente:** Acuerdo 48 de 2014 — Plan de Ordenamiento Territorial de Medellín  
**PDF:** `POT-Medellin (1).pdf` (877 páginas, ABBYY FineReader)

## Hallazgos previos a la re-extracción

La extracción original (`nodos.csv`, `nodos_v2.csv`) tenía estos problemas:

| Problema | Detalle |
|---|---|
| Contenido ausente | El campo `resumen` era idéntico al `etiqueta` en los 624 registros — **no había texto normativo de ningún artículo**, solo encabezados. |
| Encabezados truncados | 216 de 624 (~35 %) etiquetas estaban cortadas a 80 caracteres (p. ej. *"Articulo 621. Armonizacion del Documento Tecnico de Soporte y la"*). |
| Duplicados | Art. 355 aparece dos veces; Art. 412 aparece dos veces (uno legítimo y otro con etiqueta corrupta `"Articulo 412, Articulo 413 y Articulo 414"`). |
| KPI desincronizado | `kpi_pot.csv` declara `total_articulos = 624` cuando el POT tiene exactamente **622 artículos** (numerados 1–622, sin saltos). |

## Re-extracción a partir del PDF oficial

Se construyó `extract_pot_articles.py`, que:

1. Renderiza el PDF con `pdftotext -layout` (preserva la disposición de columnas).
2. Recorre el texto buscando los artículos en orden numérico (1, 2, …, 622). Esto evita falsos positivos por referencias cruzadas dentro de párrafos.
3. Detecta encabezados con tolerancia a indentación variable (hasta 8 espacios) y a la separación variable entre número y título.
4. Aísla el cuerpo de cada artículo como el texto entre su encabezado y el del siguiente.
5. Detecta los marcadores jerárquicos (`PARTE`, `TÍTULO`, `CAPÍTULO`, `SECCIÓN`) y los asocia a cada artículo.
6. Limpia los encabezados/pies de página recurrentes (`Acuerdo 48 DE 2014`, *"Por medio del cual se revisa…"*, números de página).
7. Cierra el articulado en el límite *Tabla de Contenido / ANEXO 1* para evitar que el último artículo absorba los anexos.

## Resultado de la nueva extracción

```
Artículos extraídos: 622/622
Faltantes:    ninguno
Duplicados:   ninguno
Fuera de rango: ninguno
Cuerpos <100 caracteres: [290]   ← genuino, ese artículo es así de corto en el PDF
Longitud media del cuerpo: 2 963 caracteres
```

Validaciones realizadas:

- Numeración consecutiva de **1 a 622** sin saltos.
- Sin duplicados ni números fuera de rango.
- Inspección manual de los 5 artículos más cortos (290, 587, 619, 512, 564): todos confirmados como reales en el PDF, no son errores de parseo.
- Inspección manual del artículo más largo (139 — listado de Bienes de Interés Cultural): contenido completo verificado.
- Artículo 622 (*Expedición, Vigencias y Derogatorias*) acotado correctamente a 2 138 caracteres en lugar de absorber los anexos posteriores.

## Archivos generados

| Archivo | Contenido |
|---|---|
| `articulos_pot.json` | 622 artículos con `numero`, `titulo`, `parte`, `titulo_pot`, `capitulo`, `seccion`, `texto`, `longitud`. |
| `articulos_pot.csv` | Mismo contenido en CSV. |
| `extract_pot_articles.py` | Script reproducible (requiere `poppler-utils` para `pdftotext`). |

## Integración en la visualización (`nodos_v2.csv`, `relaciones_v2.csv`, `kpi_pot.csv`)

El script `update_nodos_v2.py` aplica los datos extraídos al grafo que consume `index.html`:

- Reemplaza el campo `resumen` de las 622 filas `tipo=articulo` por el **texto íntegro** del artículo.
- Reemplaza la `etiqueta` truncada por **"Artículo N. <título completo>"** con tildes.
- Backfilla `parte`, `titulo_pot` y `capitulo_pot` cuando estaban vacíos en la fila.
- Elimina la fila `n833` (duplicado de Art. 355, sin aristas) y la fila `n15` (etiqueta corrupta `"Articulo 412, Articulo 413 y Articulo 414"`).
- Re-rutea la única arista que apuntaba a `n15` para que apunte a `n767` (el nodo legítimo de Art. 412).
- Recalcula `kpi_pot.csv`:

| Métrica | Antes | Después |
|---|---|---|
| `total_nodos` | 676 | **674** |
| `total_articulos` | 624 | **622** |
| `total_relaciones` | 747 | **746** |
| `relaciones_jerarquicas` | 308 | **307** |

`index.html` no requiere cambios: el panel de detalle ya renderiza `node.resumen` dentro de un `<p>` con `white-space: pre-wrap`, lo que preserva los saltos de línea del texto extraído.

## Cómo reproducir la extracción

```bash
# 1. Asegurarse de tener el PDF en la raíz del repo
ls "POT-Medellin (1).pdf"

# 2. Asegurarse de tener pdftotext (poppler-utils)
which pdftotext || sudo apt-get install -y poppler-utils

# 3. Ejecutar
python3 extract_pot_articles.py
```

El script imprime un reporte de validación y produce `articulos_pot.json` y `articulos_pot.csv`.
