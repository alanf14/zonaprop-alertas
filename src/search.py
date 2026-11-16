# -*- coding: utf-8 -*-
"""
Buscador de Zonaprop.

Por cada Criterio arma UNA URL con todos sus barrios y tipos de propiedad,
ordenada por mas recientes, y construye las Propiedades directo desde el listado
(window.__PRELOADED_STATE__ -> listStore.listPostings): precio, expensas,
publicador, caracteristicas y fotos ya vienen ahi. No se baja cada aviso.

Formato verificado en vivo el 16-11-2026 contra listStore.appliedFilters:
    {tipos}-{operacion}-{barrio1}-{barrio2}...-{N}-{habitaciones|ambientes}
        [-mas-{min}][-menos-{max}]-{pesos|dolar}-orden-publicado-descendente[-pagina-N].html
  - tipos juntos: "departamentos-ph-casas"
  - barrios de CABA y GBA mezclados en la misma URL
  - "vicente-lopez" = el partido entero (Olivos, Munro, Florida, ...)
  - publisherTypeId "1" = dueño directo, "2" = inmobiliaria
Ver docs/piedras-conocidas.md.
"""

from __future__ import annotations

import json
import logging
import re
import time

from fetch import PAUSA_ENTRE_REQUESTS, bajar_html
from models import Criterio, Propiedad, normalizar_texto

logger = logging.getLogger("matcher")

_BASE = "https://www.zonaprop.com.ar"

# Green flags por texto (titulo + descripcion, sin acentos).
# ponytail: busqueda de palabras con negacion simple ("no/sin" cerca); puede
# errar con frases raras. Upgrade: bajar el detalle del aviso y leer generalFeatures.
_FLAGS = {
    "Cochera": ("cochera",),
    "Apto mascotas": ("mascota",),
    "Balcón": ("balcon",),
    "Terraza": ("terraza",),
    "Ascensor": ("ascensor",),
    "Amoblado": ("amoblad", "amueblad"),
    "Pileta": ("pileta", "piscina"),
}


def _slug_barrio(barrio: str) -> str:
    """Slug del barrio: sin acentos, minusculas, espacios -> guiones."""
    return normalizar_texto(barrio).replace(" ", "-")


def _unidad_url(crit: Criterio) -> str:
    return "habitaciones" if crit.tipo_ambiente == "dormitorios" else "ambientes"


def _construir_url(crit: Criterio, valor: int | None, pagina: int = 1) -> str:
    partes = ["-".join(crit.tipos or ["departamentos"]), f"-{crit.operacion}"]
    for b in crit.barrios:
        partes.append(f"-{_slug_barrio(b)}")
    if valor is not None:
        partes.append(f"-{valor}-{_unidad_url(crit)}")
    if crit.precio_min is not None or crit.precio_max is not None:
        if crit.precio_min is not None:
            partes.append(f"-mas-{crit.precio_min}")
        if crit.precio_max is not None:
            partes.append(f"-menos-{crit.precio_max}")
        partes.append("-pesos" if crit.moneda == "ARS" else "-dolar")
    partes.append("-orden-publicado-descendente")
    if pagina > 1:
        partes.append(f"-pagina-{pagina}")
    return f"{_BASE}/{''.join(partes)}.html"


def _extraer_preloaded_state(html: str) -> dict | None:
    """Extrae y parsea window.__PRELOADED_STATE__ (JSON anidado -> raw_decode)."""
    i = html.find("window.__PRELOADED_STATE__")
    if i == -1:
        return None
    igual = html.find("=", i)
    if igual == -1:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(html[igual + 1:].lstrip())
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


# ── Posting (JSON del listado) -> Propiedad ─────────────────────
def _int(v) -> int | None:
    try:
        return int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _feature(p: dict, label: str):
    for f in (p.get("mainFeatures") or {}).values():
        if f.get("label") == label:
            return f.get("value")
    return None


def _menciona(texto: str, clave: str) -> bool:
    return any(
        not re.search(r"\b(no|sin)\b", texto[max(0, m.start() - 25):m.start()])
        for m in re.finditer(clave, texto)
    )


def _flags(p: dict) -> list[str]:
    texto = normalizar_texto(f"{p.get('title') or ''} {p.get('descriptionNormalized') or ''}")
    flags = [et for et, claves in _FLAGS.items() if any(_menciona(texto, k) for k in claves)]
    if (_int(_feature(p, "Cochera")) or 0) > 0 and "Cochera" not in flags:
        flags.insert(0, "Cochera")
    return flags


def _propiedad(p: dict) -> Propiedad | None:
    pid, url = p.get("postingId"), p.get("url")
    if pid is None or not url:
        return None

    precio, moneda = None, ""
    try:
        pr = p["priceOperationTypes"][0]["prices"][0]
        precio = _int(pr.get("amount"))
        moneda = "ARS" if pr.get("currency") == "$" else (pr.get("currency") or "")
    except (KeyError, IndexError, TypeError):
        pass

    exp = p.get("expenses") or {}
    expensas = _int(exp.get("amount")) if exp.get("currency") in ("$", None) else None

    ubicaciones, loc = [], (p.get("postingLocation") or {}).get("location")
    while loc:
        if loc.get("name"):
            ubicaciones.append(loc["name"])
        loc = loc.get("parent")

    fotos = (p.get("visiblePictures") or {}).get("pictures") or []
    return Propiedad(
        id=str(pid),
        titulo=p.get("title") or p.get("generatedTitle") or "",
        link=url if url.startswith("http") else _BASE + url,
        precio=precio,
        moneda=moneda,
        barrio=ubicaciones[0] if ubicaciones else "",
        direccion=((p.get("postingLocation") or {}).get("address") or {}).get("name") or "",
        ambientes=_int(_feature(p, "Ambientes")),
        dormitorios=_int(_feature(p, "Dormitorios")),
        m2=_int(_feature(p, "Superficie cubierta") or _feature(p, "Superficie total")),
        foto=fotos[0].get("url730x532", "") if fotos else "",
        fecha_publicacion=p.get("modified_date") or "",
        expensas=expensas,
        dueno_directo=(p.get("publisher") or {}).get("publisherTypeId") == "1",
        tipo=(p.get("realEstateType") or {}).get("name", ""),
        ubicaciones=ubicaciones,
        flags=_flags(p),
    )


def buscar(crit: Criterio, max_paginas: int = 2) -> list[Propiedad]:
    """Propiedades del listado de Zonaprop para un Criterio (mas recientes primero)."""
    if not crit.barrios:
        logger.warning("Criterio %r sin barrios: no busco (seria todo el pais)", crit.nombre_cliente)
        return []

    vistos: set[str] = set()
    resultado: list[Propiedad] = []
    for valor in crit.valores or [None]:
        for pagina in range(1, max_paginas + 1):
            url = _construir_url(crit, valor, pagina)
            time.sleep(PAUSA_ENTRE_REQUESTS)
            html = bajar_html(url)
            lista = ((_extraer_preloaded_state(html) if html else None) or {}).get("listStore") or {}
            postings = lista.get("listPostings") or []
            if not postings:
                if html:
                    logger.warning("Sin postings en %s (¿cambió el HTML?)", url)
                break
            for p in postings:
                prop = _propiedad(p)
                if prop and prop.id not in vistos:
                    vistos.add(prop.id)
                    resultado.append(prop)
            logger.info("%s pagina %s: %s postings (total %s)", crit.nombre_cliente, pagina,
                        len(postings), lista.get("totalPosting"))
            paging = lista.get("paging") or {}
            if paging.get("lastPage") or pagina >= (paging.get("totalPages") or 1):
                break

    logger.info("buscar %r: %s propiedades", crit.nombre_cliente, len(resultado))
    return resultado
