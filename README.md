# matcher-zonaprop

Avisa por Discord cuando aparece en Zonaprop una propiedad nueva que cumple una búsqueda.

## Cómo funciona
- `src/search.py` arma una URL por búsqueda (todos los barrios y tipos, orden por recientes) y lee el listado: precio, expensas, dueño directo, características y fotos.
- `src/match.py` filtra (tope con alquiler + expensas, conversión USD, sub-zonas).
- `src/store.py` recuerda qué ya se avisó (SQLite).
- `src/notify.py` manda el aviso a Discord (un canal por búsqueda vía `webhook_env`).

## Uso local
```bash
cp criterios.example.json criterios.json   # editar
cp .env.example .env                       # webhooks
python src/run.py --baseline --max-paginas 15   # 1ra vez: marca lo actual sin avisar
python src/run.py --notificar discord           # siguientes: avisa solo lo nuevo
```

## En la nube
`.github/workflows/buscar.yml` corre cada 15 min. Secrets necesarios:
`CRITERIOS_JSON`, `DISCORD_WEBHOOK_ALQUILER`, `VISTOS_KEY`. La base de vistos se guarda cifrada (`data/vistos.db.enc`) y los logs no muestran datos de la búsqueda.

Trampas conocidas de Zonaprop: `docs/piedras-conocidas.md`.
