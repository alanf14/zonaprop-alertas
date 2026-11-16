# -*- coding: utf-8 -*-
"""
Capa de notificacion (Tanda 2).

Backends intercambiables detras de una interfaz comun, igual que providers/ en
whatsapp-agentkit. Hoy solo esta implementado el backend de SIMULACION (consola).
El backend real (Twilio / WhatsApp Business API) queda como stub documentado y se
implementa cuando se ejecute la Tanda 2.

Import plano (vive en src/).
"""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod

import requests

from models import Propiedad

logger = logging.getLogger("matcher")


def _miles(n: int | float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def _descr_tamanio(prop: Propiedad) -> str:
    """'Departamentos · 4 amb · 3 dorm · 90 m²' segun lo que tenga el aviso."""
    partes = [prop.tipo] if prop.tipo else []
    if prop.ambientes is not None:
        partes.append(f"{prop.ambientes} amb")
    if prop.dormitorios is not None:
        partes.append(f"{prop.dormitorios} dorm")
    if prop.m2:
        partes.append(f"{_miles(prop.m2)} m²")
    return " · ".join(partes) or "N/D"


def _descr_precio(prop: Propiedad) -> str:
    """'$ 1.500.000 + $ 300.000 exp. = $ 1.800.000' (total solo si todo es en pesos)."""
    if prop.precio is None:
        return "consultar"
    simbolo = "$" if prop.moneda == "ARS" else prop.moneda
    txt = f"{simbolo} {_miles(prop.precio)}"
    if prop.expensas:
        txt += f" + $ {_miles(prop.expensas)} exp."
        if prop.moneda == "ARS":
            txt += f" = $ {_miles(prop.precio + prop.expensas)}"
    elif prop.moneda == "ARS":
        txt += " (expensas no informadas)"
    return txt


def _encabezado(prop: Propiedad, criterio_nombre: str) -> str:
    if prop.dueno_directo:
        return f"⭐ DUEÑO DIRECTO — nueva propiedad para *{criterio_nombre}*"
    return f"🏠 Nueva propiedad para *{criterio_nombre}*"


def formatear_aviso(prop: Propiedad, criterio_nombre: str) -> str:
    """Texto plano del aviso (consola / WhatsApp)."""
    lineas = [
        _encabezado(prop, criterio_nombre),
        "",
        f"*{prop.titulo}*",
        f"💵 {_descr_precio(prop)}",
        f"📍 {prop.barrio or 'N/D'} · {_descr_tamanio(prop)}",
    ]
    if prop.flags:
        lineas.append(f"🟢 {' · '.join(prop.flags)}")
    lineas.append(f"🔗 {prop.link}")
    return "\n".join(lineas)


class NotificadorBase(ABC):
    """Interfaz que todo backend de notificacion debe implementar."""

    @abstractmethod
    def enviar(self, mensaje: str) -> bool:
        """Envia un mensaje de texto. Devuelve True si fue exitoso."""
        ...

    def enviar_aviso(self, prop: Propiedad, criterio_nombre: str) -> bool:
        """Envia el aviso de una propiedad.

        Por defecto usa el texto plano de formatear_aviso. Los backends que
        soporten formato rico (ej. Discord con imagen) sobrescriben este metodo.
        """
        return self.enviar(formatear_aviso(prop, criterio_nombre))


class NotificadorConsola(NotificadorBase):
    """Backend de SIMULACION: no manda nada, imprime el mensaje tal cual saldria.

    Sirve para probar el flujo y el formato sin depender de WhatsApp.
    """

    def enviar(self, mensaje: str) -> bool:
        print("┌─ [SIMULACION WhatsApp] ─────────────────────────────")
        for linea in mensaje.splitlines():
            print(f"│ {linea}")
        print("└─────────────────────────────────────────────────────")
        return True


class NotificadorDiscord(NotificadorBase):
    """Backend REAL vía Discord Webhook.

    El canal mas simple para un MVP: NO requiere bot, token ni verificacion.
    Solo un webhook URL de un canal de Discord (Configuracion del canal ->
    Integraciones -> Webhooks -> Nuevo webhook -> Copiar URL).

    La URL es un secreto (quien la tenga puede postear al canal): se lee de la
    variable de entorno DISCORD_WEBHOOK_URL, nunca se hardcodea.
    """

    # WhatsApp usa *negrita* (un asterisco); Discord usa **negrita** (doble).
    _RE_BOLD = re.compile(r"\*([^*\n]+)\*")

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")

    def _a_markdown_discord(self, mensaje: str) -> str:
        """Convierte la negrita estilo WhatsApp (*x*) a estilo Discord (**x**)."""
        return self._RE_BOLD.sub(r"**\1**", mensaje)

    def enviar(self, mensaje: str) -> bool:
        if not self.webhook_url:
            logger.error(
                "DISCORD_WEBHOOK_URL no configurado; no se puede enviar a Discord."
            )
            return False
        contenido = self._a_markdown_discord(mensaje)
        try:
            r = requests.post(self.webhook_url, json={"content": contenido}, timeout=15)
        except requests.RequestException as error:
            # Solo el tipo: el mensaje puede incluir la URL del webhook (secreta).
            logger.error("Error enviando a Discord: %s", type(error).__name__)
            return False
        # Discord responde 204 No Content cuando el webhook fue exitoso.
        if r.status_code not in (200, 204):
            logger.error("Discord devolvio status %s: %s", r.status_code, r.text)
            return False
        return True

    def enviar_aviso(self, prop: Propiedad, criterio_nombre: str) -> bool:
        """Envia el aviso como un embed rico de Discord, con la imagen del aviso."""
        if not self.webhook_url:
            logger.error("DISCORD_WEBHOOK_URL no configurado; no se puede enviar a Discord.")
            return False

        campos = [
            {"name": "💵 Precio", "value": _descr_precio(prop), "inline": False},
            {"name": "📍 Ubicación", "value": f"{prop.barrio or 'N/D'} · {_descr_tamanio(prop)}",
             "inline": False},
        ]
        if prop.flags:
            campos.append({"name": "🟢 Green flags", "value": " · ".join(prop.flags), "inline": False})

        embed = {
            "title": (prop.titulo or "Nueva propiedad")[:256],
            "url": prop.link,
            "color": 0xF1C40F if prop.dueno_directo else 0x2ECC71,  # dorado = dueño directo
            "fields": campos,
            "footer": {"text": f"Aviso: {criterio_nombre}"},
        }
        if prop.foto:
            embed["image"] = {"url": prop.foto}

        payload = {
            "content": self._a_markdown_discord(_encabezado(prop, criterio_nombre)),
            "embeds": [embed],
        }
        try:
            r = requests.post(self.webhook_url, json=payload, timeout=15)
        except requests.RequestException as error:
            # Solo el tipo: el mensaje puede incluir la URL del webhook (secreta).
            logger.error("Error enviando aviso a Discord: %s", type(error).__name__)
            return False
        if r.status_code not in (200, 204):
            logger.error("Discord devolvio status %s: %s", r.status_code, r.text)
            return False
        return True


class NotificadorTwilio(NotificadorBase):
    """Backend REAL vía Twilio WhatsApp (Tanda 2 — NO implementado todavia).

    Cuando se ejecute la Tanda 2:
      - leer TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_PHONE_NUMBER del entorno
      - destino = numero propio del broker (Modo A: el sistema avisa al broker)
      - POST a https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json
    """

    def enviar(self, mensaje: str) -> bool:
        raise NotImplementedError(
            "NotificadorTwilio se implementa en la Tanda 2 (envio real por WhatsApp)."
        )


def obtener_notificador(modo: str = "consola") -> NotificadorBase:
    """Factory: 'consola' (simulacion), 'discord' (real, MVP) o 'twilio' (Tanda 2)."""
    if modo == "consola":
        return NotificadorConsola()
    if modo == "discord":
        return NotificadorDiscord()
    if modo == "twilio":
        return NotificadorTwilio()
    raise ValueError(f"Modo de notificador no soportado: {modo!r}")
