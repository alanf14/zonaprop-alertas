# -*- coding: utf-8 -*-
"""
Orquestador end-to-end del motor matcher-zonaprop.

Flujo por criterio:
  1. buscar_ids(crit) -> lista de (id, url).
  2. Filtrar los NUEVOS (es_nuevo == True).
  3. Por cada nuevo: bajar detalle, parsear, matchear. SIEMPRE marcar visto
     (matchee o no) para no reprocesarlo en corridas futuras.
  4. Escribir salidas/nuevas_YYYYMMDD_HHMM.json e imprimir resumen legible.

Modo --baseline: marca como vistos TODOS los ids encontrados SIN bajar detalle
ni alertar. Sirve para "sembrar" la base la primera vez.

Uso:
    python src/run.py                    # corrida normal (data/vistos.db)
    python src/run.py --baseline         # siembra la base
    python src/run.py --db data/smoke.db --barrio Belgrano --max-paginas 1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Rutas ABSOLUTAS respecto de la raiz del proyecto (no del cwd) ──
RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Carga variables de entorno desde matcher-zonaprop/.env (ej. DISCORD_WEBHOOK_URL).
# Es opcional: si no esta python-dotenv o no hay .env, sigue funcionando.
try:
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
except ImportError:
    pass

from models import Criterio, Propiedad  # noqa: E402
from match import matchea  # noqa: E402
from store import conectar, es_nuevo, marcar_visto  # noqa: E402
from search import buscar  # noqa: E402
from notify import NotificadorBase, NotificadorDiscord, obtener_notificador  # noqa: E402

logger = logging.getLogger("matcher")

DB_DEFAULT = RAIZ / "data" / "vistos.db"
SALIDAS_DIR = RAIZ / "salidas"
CRITERIOS_PATH = RAIZ / "criterios.json"


def cargar_criterios(path: Path) -> list[Criterio]:
    """Carga criterios.json -> lista de Criterio."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Criterio.from_dict(d) for d in data.get("criterios", [])]


def _imprimir_match(prop: Propiedad) -> None:
    """Resumen legible del aviso, con EXACTAMENTE los campos que pidio el cliente."""
    precio = (
        f"{prop.moneda} {prop.precio:,}".strip()
        if prop.precio is not None
        else "sin precio"
    )
    print("-" * 60)
    print(f"Titulo:    {prop.titulo}")
    print(f"Precio:    {precio}")
    print(f"Ubicacion: {prop.barrio or 'N/D'}")
    print(f"Ambientes: {prop.ambientes if prop.ambientes is not None else 'N/D'}")
    print(f"Link:      {prop.link}")


def ejecutar(
    criterios: list[Criterio],
    db_path: str | Path,
    max_paginas: int = 5,
    baseline: bool = False,
    salidas_dir: str | Path = SALIDAS_DIR,
    notificador: NotificadorBase | None = None,
    fallos: list[str] | None = None,
) -> dict:
    """Corre el flujo completo. Devuelve dict {criterio: [prop.to_dict(), ...]}.

    Diseniada para ser invocable directamente desde tests con una DB descartable.

    Si se pasa un `notificador`, por cada match se envia el aviso de WhatsApp
    (con el backend elegido: consola=simulacion, twilio=real en Tanda 2).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    salidas_dir = Path(salidas_dir)

    conn = conectar(str(db_path))
    matches_por_criterio: dict[str, list[dict]] = {}

    try:
        for crit in criterios:
            logger.info("=== Criterio: %s ===", crit.nombre_cliente)
            props = buscar(crit, max_paginas=max_paginas)
            if not props and fallos is not None:
                fallos.append(crit.nombre_cliente)  # 0 resultados = bloqueo o cambio de HTML

            if baseline:
                # Sembrar: marcar TODO como visto sin alertar.
                sembrados = 0
                for prop in props:
                    if es_nuevo(conn, prop.id):
                        marcar_visto(conn, prop, crit.nombre_cliente)
                        sembrados += 1
                logger.info(
                    "Baseline %r: %s ids sembrados como vistos", crit.nombre_cliente, sembrados
                )
                matches_por_criterio.setdefault(crit.nombre_cliente, [])
                continue

            # Webhook propio del criterio (ej. canal de alquiler). Si falta, se saltea
            # el criterio entero: mejor no avisar que avisar en el canal equivocado.
            noti = notificador
            if isinstance(notificador, NotificadorDiscord) and crit.webhook_env:
                url = os.getenv(crit.webhook_env)
                if not url:
                    logger.error("Falta %s en el entorno; salteo ese criterio", crit.webhook_env)
                    continue
                noti = NotificadorDiscord(url)

            nuevos = [p for p in props if es_nuevo(conn, p.id)]
            logger.info("Criterio %r: %s nuevos (no vistos)", crit.nombre_cliente, len(nuevos))

            matches: list[dict] = []
            cant_match = 0
            for prop in nuevos:
                if matchea(prop, crit):
                    _imprimir_match(prop)
                    if noti is not None and not noti.enviar_aviso(prop, crit.nombre_cliente):
                        # No se marca visto: se reintenta en la proxima corrida.
                        logger.warning("No se pudo avisar %s; reintento la próxima", prop.id)
                        continue
                    matches.append(prop.to_dict())
                    cant_match += 1
                marcar_visto(conn, prop, crit.nombre_cliente)

            logger.info(
                "Criterio %r: %s matchean de %s nuevos",
                crit.nombre_cliente, cant_match, len(nuevos),
            )
            matches_por_criterio[crit.nombre_cliente] = matches

        # Escribir salida solo si hubo avisos (corre cada 15 min: sin archivos vacios).
        if not baseline and any(matches_por_criterio.values()):
            salidas_dir.mkdir(parents=True, exist_ok=True)
            marca = datetime.now().strftime("%Y%m%d_%H%M%S")
            salida_path = salidas_dir / f"nuevas_{marca}.json"
            with open(salida_path, "w", encoding="utf-8") as f:
                json.dump(matches_por_criterio, f, ensure_ascii=False, indent=2)
            total = sum(len(v) for v in matches_por_criterio.values())
            logger.info("Salida escrita: %s (%s matches)", salida_path, total)
            print(f"\nSalida: {salida_path}  ({total} matches)")

        return matches_por_criterio
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Motor matcher-zonaprop")
    parser.add_argument("--db", default=str(DB_DEFAULT), help="Ruta a la DB SQLite de vistos")
    parser.add_argument("--baseline", action="store_true", help="Sembrar base sin alertar")
    parser.add_argument("--max-paginas", type=int, default=5, help="Maximo de paginas por barrio")
    parser.add_argument("--barrio", default=None, help="Forzar un solo barrio (para pruebas)")
    parser.add_argument("--criterios", default=str(CRITERIOS_PATH), help="Ruta a criterios.json")
    parser.add_argument(
        "--notificar",
        choices=["consola", "discord", "twilio"],
        default=None,
        help="Enviar aviso por cada match: 'consola' (simulacion), 'discord' (real, MVP) o 'twilio' (Tanda 2)",
    )
    args = parser.parse_args(argv)

    # La consola de Windows suele ser cp1252; forzamos UTF-8 para no romper
    # con titulos acentuados u otros caracteres del aviso.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    # En la nube LOG_LEVEL=ERROR: los logs de un repo publico son publicos y los
    # INFO/WARNING muestran barrios, precios y URLs de la busqueda.
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    criterios = cargar_criterios(Path(args.criterios))
    if args.barrio:
        # Para pruebas: restringir todos los criterios a un solo barrio.
        for c in criterios:
            c.barrios = [args.barrio]

    notificador = obtener_notificador(args.notificar) if args.notificar else None

    fallos: list[str] = []
    ejecutar(
        criterios,
        db_path=args.db,
        max_paginas=args.max_paginas,
        baseline=args.baseline,
        notificador=notificador,
        fallos=fallos,
    )
    if fallos:
        # Sin nombres: el log puede ser publico. Exit 1 = la corrida sale en rojo.
        logger.error("%s busqueda(s) sin resultados (¿bloqueo de Zonaprop?)", len(fallos))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
