# Piedras conocidas — matcher-zonaprop

Trampas que costaron tiempo. Leer al arrancar sesión. Una línea + fecha + método.

- **La URL que copia el usuario ≠ la que asumimos** (27-07-2026, link real copiado del navegador): multi-barrio, `N-habitaciones` = dormitorios, superficie `mas-80-m2-cubiertos`, precio `X-Y-dolar`, querystring utm. Ver `link_parser.py`.
- **Verificar filtros con `listStore.appliedFilters`, no con "trajo 30 resultados"** (16-11-2026): Zonaprop puede ignorar un segmento y mostrar todo igual.
- **El listado ya trae todo** (16-11-2026, `listPostings`): precio, `expenses`, `publisher.publisherTypeId` ("1" = dueño directo, "2" = inmobiliaria), `mainFeatures` (Ambientes, Dormitorios, Cochera, m²), fotos. No hace falta bajar cada aviso.
- **Amenities (mascotas, balcón, pileta, ascensor, amoblado) NO vienen en el listado** (16-11-2026): se detectan por texto en título + `descriptionNormalized` (heurística con negación).
- **Sub-zonas y partidos** (16-11-2026): avisos vienen como "Belgrano R > Belgrano", "Lomas de Núñez > Núñez", "Olivos > Vicente López". `vicente-lopez` en la URL = partido entero. Matchear contra la cadena de ubicación, no solo el nombre más profundo.
- **El filtro `-menos-2000000-pesos` deja pasar avisos en USD** (16-11-2026): Zonaprop convierte. Para sumar expensas hay que convertir con `usd_ars` del criterio.
- **En venta, Zonaprop ignora el `-mas-{min}` si va junto a `-menos-{max}-dolar`** (16-11-2026, appliedFilters muestra solo el tope). El mínimo lo filtra `match.py`.
- **403 desde la página 10** (16-11-2026, baseline venta): Zonaprop corta la paginación profunda. Para corridas periódicas alcanza con 2 páginas ordenando por `-orden-publicado-descendente`.
- **Zonaprop bloquea IPs de data center** (16-11-2026, workflow de diagnóstico en GitHub Actions, curl y requests): `403` + `cf-mitigated: challenge` ("Just a moment…") de Cloudflare, incluso en la home. Desde IP residencial: `200`. GitHub Actions NO sirve para scrapear Zonaprop. No evadir el anti-bot.
- **GitHub enmascara cada LÍNEA de un Secret multilínea** (16-11-2026): un JSON con indentación y una línea "3" hace que todos los "3" del log salgan `***`. Cargar JSON compacto en una línea.
- **Argenprop: anti-bot de AWS WAF** (16-11-2026, curl): desde IP de casa `202` + `x-amzn-waf-action: challenge` (pide JavaScript); desde GitHub `405` + `captcha`. No se puede leer sin evadir el anti-bot → descartado para automatizar.
- **MercadoLibre web desde la nube = página sin avisos** (16-11-2026, diagnóstico GitHub): `200` pero 136 KB sin `initialState` (desde casa: 2 MB con resultados, expensas y "Dueño directo").
- **MercadoLibre API: llega desde la nube pero pide token** (16-11-2026): `/sites/MLA/search?category=MLA1459` → `403 forbidden` de ML (no anti-bot), igual desde casa. La guía oficial "Localizar Inmuebles" documenta esa búsqueda con `Authorization: Bearer`. Token por OAuth `authorization_code` + `refresh_token` (no hay client_credentials en la doc).
