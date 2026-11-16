# -*- coding: utf-8 -*-
"""
Descarga de HTML de avisos de Zonaprop.
Maneja reintentos con backoff exponencial y logging de fallos.
La pausa entre requests (rate-limit) la respeta el orquestador, NO este modulo.
"""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger("matcher")

# Pausa recomendada entre requests sucesivas (segundos). El orquestador
# debe hacer time.sleep(PAUSA_ENTRE_REQUESTS) entre llamadas a bajar_html.
PAUSA_ENTRE_REQUESTS = 1.5

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}


def bajar_html(url: str, timeout: int = 20, reintentos: int = 3) -> str | None:
    """Descarga el HTML de una URL con reintentos y backoff exponencial.

    Devuelve el texto del HTML si la respuesta es 200, o None si tras
    agotar los reintentos no se pudo obtener una respuesta valida.
    """
    espera = 1
    for intento in range(1, reintentos + 1):
        try:
            respuesta = requests.get(url, headers=_HEADERS, timeout=timeout)
        except requests.RequestException as error:
            logger.warning(
                "Intento %s/%s fallo para %s: %s", intento, reintentos, url, error
            )
        else:
            if respuesta.status_code == 200:
                return respuesta.text
            logger.warning(
                "Intento %s/%s para %s devolvio status %s",
                intento,
                reintentos,
                url,
                respuesta.status_code,
            )

        if intento < reintentos:
            time.sleep(espera)
            espera *= 2

    logger.warning("Se agotaron los reintentos para %s", url)
    return None
