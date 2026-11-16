# -*- coding: utf-8 -*-
"""
Parser inverso de URLs de busqueda de Zonaprop -> parametros de Criterio.

Dado un link de busqueda (el que copia el usuario del navegador), extrae lo que
pueda (operacion, barrios, ambientes/dormitorios, precio). Devuelve SOLO lo que
reconoce; lo que falta queda para que el flujo conversacional lo pregunte.

Zonaprop usa URLs SEO con multiples variantes. Este parser maneja el formato
REAL de la web (verificado con link real 2026-07-27), por ejemplo:

    departamentos-saavedra-belgrano-nunez-colegiales-3-habitaciones\
    -mas-80-m2-cubiertos-100005-240000-dolar.html?utm_source=...

    -> {operacion? , barrios: [Saavedra, Belgrano, Nunez, Colegiales],
        dormitorios: 3, precio_min: 100005, precio_max: 240000, moneda: USD}

y tambien el formato que arma search.py:

    departamentos-venta-belgrano-4-ambientes-mas-170000-menos-230000-dolar.html
    -> {operacion: venta, barrios: [Belgrano], ambientes: 4,
        precio_min: 170000, precio_max: 230000, moneda: USD}

Limitacion conocida: los barrios compuestos ("villa-crespo") se parten en dos
porque no hay diccionario de barrios. El flujo muestra lo reconocido para que el
usuario corrija si hace falta.
"""

from __future__ import annotations

import re

# Tipos de propiedad que Zonaprop pone como prefijo del slug.
_TIPOS = r"(?:departamentos|departamento|casas|casa|ph|deptos)"

# Primer "token de filtro": marca donde terminan los barrios y empiezan los filtros.
_RE_INICIO_FILTROS = re.compile(
    r"-(\d+-(?:ambientes|habitaciones)|mas-\d+|menos-\d+|\d+-\d+-(?:dolar|dolares|pesos))-"
)


def _slug_a_barrio(slug: str) -> str:
    """'nunez' -> 'Nunez' (para mostrar; el match normaliza acentos igual)."""
    return slug.capitalize()


def es_link_zonaprop(texto: str) -> bool:
    """True si el texto parece una URL de busqueda de Zonaprop."""
    t = texto.strip().lower()
    return "zonaprop.com.ar" in t and t.startswith("http")


def parsear_link(url: str) -> dict:
    """Extrae los parametros reconocibles de una URL de busqueda de Zonaprop."""
    # 1) Limpiar: sacar querystring/fragment, dominio y extension.
    path = url.split("?", 1)[0].split("#", 1)[0]
    seg = path.rstrip("/").rsplit("/", 1)[-1]
    if seg.endswith(".html"):
        seg = seg[:-5]
    # Rodear de guiones para que los regex de bordes sean uniformes.
    s = "-" + seg.lower() + "-"

    datos: dict = {}

    # 2) Operacion (opcional; a veces el link no la trae).
    m = re.search(r"-(venta|alquiler)-", s)
    if m:
        datos["operacion"] = m.group(1)

    # 3) Superficie: reconocerla para NO confundirla con el precio.
    #    (No se usa en el Criterio; solo se remueve antes de parsear precio.)
    s_sin_sup = re.sub(r"-(?:mas|menos)-\d+-m2(?:-cubiertos|-totales)?", "-", s)

    # 4) Precio. Dos formatos posibles:
    #    a) rango directo:  {min}-{max}-dolar
    #    b) mas/menos:      mas-{min}-...-menos-{max}-dolar
    pmin = pmax = None
    m = re.search(r"-(\d+)-(\d+)-(?:dolar|dolares|pesos)-", s_sin_sup)
    if m:
        pmin, pmax = int(m.group(1)), int(m.group(2))
    else:
        mmin = re.search(r"-mas-(\d+)-(?:dolar|dolares|pesos|menos)", s_sin_sup)
        mmax = re.search(r"-menos-(\d+)-(?:dolar|dolares|pesos)", s_sin_sup)
        if mmin:
            pmin = int(mmin.group(1))
        if mmax:
            pmax = int(mmax.group(1))
    if pmin is not None:
        datos["precio_min"] = pmin
    if pmax is not None:
        datos["precio_max"] = pmax
    if pmin is not None or pmax is not None or "-dolar" in s:
        datos["moneda"] = "USD"

    # 5) Ambientes y/o dormitorios (habitaciones).
    m = re.search(r"-(\d+)-ambientes-", s)
    if m:
        datos["ambientes"] = int(m.group(1))
    m = re.search(r"-(\d+)-habitaciones-", s)
    if m:
        datos["dormitorios"] = int(m.group(1))

    # 6) Barrios: los segmentos entre el tipo(+operacion) y el primer filtro.
    mfilt = _RE_INICIO_FILTROS.search(s)
    zona = s[: mfilt.start()] if mfilt else s
    zona = re.sub(r"^-" + _TIPOS + r"-", "-", zona)
    zona = re.sub(r"^-(?:venta|alquiler)-", "-", zona)
    barrios = [b for b in zona.strip("-").split("-") if b]
    if barrios:
        datos["barrios"] = [_slug_a_barrio(b) for b in barrios]

    return datos
