# -*- coding: utf-8 -*-
"""
Bot de Discord para configurar avisos de forma conversacional.

Escucha mensajes y permite al usuario:
  - "configurar aviso"  -> inicia el flujo guiado paso a paso.
  - pegar un link de Zonaprop -> precarga lo que pueda y pregunta el resto.
  - "mis avisos"        -> lista las busquedas guardadas.
  - "cancelar"          -> aborta la configuracion en curso.
  - "ayuda"             -> muestra los comandos.

Mantiene UNA sesion de configuracion por usuario (en memoria). La logica de
preguntas vive en config_flow.py (agnostica de Discord); aca solo esta el
transporte. El dia de maniana el mismo flujo se reusa en WhatsApp.

Correr:  python src/bot.py   (necesita DISCORD_BOT_TOKEN en .env)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from pathlib import Path

import discord
from discord.ext import tasks

# ── Rutas / imports planos (igual que run.py) ──
RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
except ImportError:
    pass

import criterios_store as cs  # noqa: E402
import run  # noqa: E402  (orquestador del motor de busqueda)
from config_flow import FlujoConfig  # noqa: E402
from link_parser import es_link_zonaprop, parsear_link  # noqa: E402
from models import Criterio  # noqa: E402
from notify import obtener_notificador  # noqa: E402
from store import conectar  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] bot: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bot")

CRITERIOS_PATH = RAIZ / "criterios.json"
DB_PATH = run.DB_DEFAULT  # misma DB de "vistos" que usa run.py manual
# Cada cuantas horas corre la busqueda automatica (configurable en .env).
INTERVALO_HORAS = float(os.getenv("INTERVALO_BUSQUEDA_HORAS", "1"))

# Sesiones de configuracion activas: user_id -> FlujoConfig.
_sesiones: dict[int, FlujoConfig] = {}

# Serializa las corridas del matcher (periodica, on-demand y baseline) para que
# no se pisen sobre la misma DB SQLite.
_matcher_lock = asyncio.Lock()


def _db_vacia() -> bool:
    """True si la DB de 'vistos' no existe o esta vacia (nunca hubo baseline)."""
    if not Path(DB_PATH).exists():
        return True
    conn = conectar(str(DB_PATH))
    try:
        return conn.execute("SELECT COUNT(*) FROM vistos").fetchone()[0] == 0
    finally:
        conn.close()


async def _correr_matcher(criterios, baseline=False, notificador=None) -> None:
    """Corre el motor en un thread (no bloquea el bot) y serializa el acceso a la DB."""
    async with _matcher_lock:
        await asyncio.to_thread(
            run.ejecutar, criterios, str(DB_PATH),
            baseline=baseline, notificador=notificador,
        )

# WhatsApp usa *negrita*; Discord usa **negrita**. Adaptamos al mostrar.
_RE_BOLD = re.compile(r"\*([^*\n]+)\*")


def _fmt(mensaje: str) -> str:
    """Adapta la negrita estilo WhatsApp (*x*) al estilo Discord (**x**)."""
    return _RE_BOLD.sub(r"**\1**", mensaje)


AYUDA = (
    "👋 Soy el bot de avisos de propiedades. Podés:\n"
    "• **configurar aviso** — te hago unas preguntas y armo tu búsqueda.\n"
    "• **pegar un link de Zonaprop** — reconozco los filtros y completás el resto.\n"
    "• **mis avisos** — te muestro las búsquedas guardadas.\n"
    "• **buscar ahora** — fuerzo una búsqueda al toque (además busco solo cada tanto).\n"
    "• **cancelar** — corta la configuración en curso.\n"
    "• **ayuda** — muestro esto de nuevo."
)


def _texto_mis_avisos() -> str:
    criterios = cs.listar(CRITERIOS_PATH)
    if not criterios:
        return "No tenés avisos guardados todavía. Escribí **configurar aviso** para crear uno."
    lineas = ["📋 **Tus avisos guardados:**"]
    for raw in criterios:
        c = Criterio.from_dict(raw)  # normaliza el esquema (viejo o nuevo)
        precio = "sin filtro"
        if c.precio_min is not None or c.precio_max is not None:
            mn = c.precio_min or 0
            mx = c.precio_max or "∞"
            precio = f"{c.moneda} {mn}–{mx}"
        barrios = ", ".join(c.barrios) or "—"
        tamanio = (
            f"{' o '.join(str(v) for v in c.valores)} {c.tipo_ambiente}"
            if c.valores else "cualquier tamaño"
        )
        lineas.append(
            f"• **{c.nombre_cliente}**: {c.operacion} · {tamanio} · {barrios} · {precio}"
        )
    return "\n".join(lineas)


intents = discord.Intents.default()
intents.message_content = True  # Requiere activar el intent en el Developer Portal.
client = discord.Client(intents=intents)


@tasks.loop(hours=INTERVALO_HORAS)
async def buscar_periodico():
    """Corre el matcher sobre todos los criterios y avisa lo nuevo. Cada INTERVALO_HORAS."""
    criterios = run.cargar_criterios(CRITERIOS_PATH)
    if not criterios:
        logger.info("Busqueda periodica: sin criterios configurados.")
        return
    logger.info("Busqueda periodica: %s criterios.", len(criterios))
    await _correr_matcher(criterios, notificador=obtener_notificador("discord"))


@buscar_periodico.before_loop
async def _antes_de_buscar():
    """Espera a que el bot este listo y siembra baseline si es la primera vez."""
    await client.wait_until_ready()
    if _db_vacia():
        criterios = run.cargar_criterios(CRITERIOS_PATH)
        if criterios:
            logger.info("Primera corrida: baseline inicial (marca lo actual sin avisar).")
            await _correr_matcher(criterios, baseline=True)


@client.event
async def on_ready():
    logger.info("Conectado como %s (id %s)", client.user, client.user.id)
    if not buscar_periodico.is_running():
        buscar_periodico.start()
    logger.info(
        "Bot escuchando. Busqueda automatica cada %s h. Escribí 'configurar aviso' o 'buscar ahora'.",
        INTERVALO_HORAS,
    )


@client.event
async def on_message(message: discord.Message):
    # Ignorar los mensajes del propio bot (evita loops).
    if message.author == client.user:
        return

    texto = (message.content or "").strip()
    if not texto:
        return

    uid = message.author.id
    t = texto.lower()

    # 1) Si el usuario ya está en un flujo activo, todo lo que escribe va al flujo.
    if uid in _sesiones:
        resultado = _sesiones[uid].recibir(texto)
        await message.channel.send(_fmt(resultado.mensaje))
        if resultado.estado == "completo":
            cs.agregar(CRITERIOS_PATH, resultado.criterio, creado_por=f"discord:{uid}")
            logger.info("Criterio guardado por %s: %s", uid, resultado.criterio.nombre_cliente)
            del _sesiones[uid]
            # Baseline del criterio nuevo: marcar lo que YA existe como visto, para
            # avisarte solo lo que aparezca de ahora en adelante (no spamear el inventario).
            await message.channel.send(
                "⏳ Reviso el inventario actual para avisarte solo lo *nuevo* de acá en adelante..."
            )
            await _correr_matcher([resultado.criterio], baseline=True)
            await message.channel.send("Tu aviso ya está activo. ✅")
        elif resultado.estado == "cancelado":
            del _sesiones[uid]
        return

    # 2) Comandos que arrancan algo (solo si NO hay sesión activa).
    if es_link_zonaprop(texto):
        datos = parsear_link(texto)
        flujo = FlujoConfig(datos_previos=datos)
        _sesiones[uid] = flujo
        await message.channel.send(_fmt(flujo.mensaje_inicial()))
        return

    if t in ("configurar aviso", "configurar", "nuevo aviso", "!configurar"):
        flujo = FlujoConfig()
        _sesiones[uid] = flujo
        await message.channel.send(_fmt(flujo.mensaje_inicial()))
        return

    if t in ("mis avisos", "listar", "avisos", "!avisos"):
        await message.channel.send(_texto_mis_avisos())
        return

    if t in ("buscar ahora", "buscar", "!buscar"):
        criterios = run.cargar_criterios(CRITERIOS_PATH)
        if not criterios:
            await message.channel.send("No tenés búsquedas configuradas. Escribí **configurar aviso**.")
            return
        await message.channel.send("🔎 Buscando en Zonaprop ahora mismo... (puede tardar un momento)")
        await _correr_matcher(criterios, notificador=obtener_notificador("discord"))
        await message.channel.send("✅ Listo. Si apareció algo nuevo que matchee, ya te lo avisé arriba.")
        return

    if t in ("ayuda", "help", "!ayuda", "hola"):
        await message.channel.send(AYUDA)
        return

    # 3) Cualquier otro mensaje suelto se ignora (para no responder a todo el canal).


def main() -> int:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("Falta DISCORD_BOT_TOKEN en el .env")
        return 1
    client.run(token, log_handler=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
