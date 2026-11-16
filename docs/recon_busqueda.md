# Recon: búsqueda y paginación en Zonaprop

> **DESACTUALIZADO (16-11-2026):** ahora se usa UNA URL con varios barrios y
> tipos, orden por recientes, y los datos salen del listado sin bajar cada
> aviso. Formato vigente en el docstring de `src/search.py`; trampas en
> `docs/piedras-conocidas.md`. Lo de abajo queda como historial.

Verificado a mano (curl con User-Agent de navegador) el 2026-07-26. Para `search.py`.

## 1. Acceso
- Zonaprop devuelve **403** sin User-Agent. Con UA de navegador → **200**.
- UA que funciona: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36`
- Header recomendado: `Accept-Language: es-AR,es;q=0.9`
- Usar `fetch.bajar_html()` (ya implementado) para todas las descargas.

## 2. URL de búsqueda (semántica, un barrio por URL)
Patrón confirmado:
```
https://www.zonaprop.com.ar/departamentos-venta-{barrio}-{N}-ambientes[-mas-{min}][-menos-{max}-dolar].html
```
- `{barrio}`: slug en minúsculas, sin acentos, espacios→guiones (ej. "Belgrano"→`belgrano`, "Núñez"→`nunez`).
- `{N}-ambientes`: cantidad de ambientes.
- Precio: `-mas-170000` (mínimo) y/o `-menos-230000-dolar` (máximo). OJO: es `dolar` singular; `dolares` da 301.
- Ejemplo válido probado (200): `https://www.zonaprop.com.ar/departamentos-venta-belgrano-4-ambientes.html`
- **Un barrio por URL**: hay que iterar los barrios del criterio y unir resultados.
- **Verificar en la implementación** la sintaxis exacta cuando hay mín Y máx juntos (el redirect observado sugiere que el orden/combinación puede variar). Construir y validar contra 200.

## 3. Extracción de resultados (robusta, vía JSON)
La página de resultados embebe `window.__PRELOADED_STATE__ = {...}` con la lista completa.
- Ruta al array: `listStore.listPostings` (30 postings por página en la prueba).
- Cada posting trae, entre otros campos: `postingId`, `url`, `title`, `priceOperationTypes`, `mainFeatures`, `postingLocation`, `antiquity`, `modified_date`.
- **Estrategia recomendada para search.py**: parsear ese JSON y devolver, por cada posting, `(id, url_absoluta)`. `url` suele ser relativa → anteponer `https://www.zonaprop.com.ar`.
- Fallback si el JSON cambia: regex sobre el HTML `"/clasificado/[a-z0-9-]+-(\d{7,})\.html"` para sacar ids+urls.

## 4. Paginación
- Zonaprop pagina con sufijo `-pagina-N` antes del `.html` (ej. `...-4-ambientes-pagina-2.html`). **Confirmar en implementación** (no verificado a fondo). Cortar cuando una página no trae postings nuevos o se llega a un máximo configurable (ej. 5 páginas) para no abusar.

## 5. Decisión de diseño para el orquestador
- `search.py` devuelve solo `(id, url)` por posting; el **detalle completo** (precio exacto, m², fecha) lo baja `run.py` con `fetch.bajar_html()` + `parse.parsear_propiedad()` SOLO para los ids nuevos (no vistos en store). Así se minimizan requests de detalle.
- Respetar `fetch.PAUSA_ENTRE_REQUESTS` entre descargas.
