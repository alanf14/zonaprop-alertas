# -*- coding: utf-8 -*-
"""
Test de search real contra Zonaprop (requests de verdad, no fixtures).
Valida la URL multi-barrio/multi-tipo y que las Propiedades salgan completas
desde el listado. Uso: python tests/test_search.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from models import Criterio  # noqa: E402
from search import _construir_url, buscar  # noqa: E402


def test_buscar_alquiler():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    crit = Criterio(
        nombre_cliente="TEST alquiler", operacion="alquiler",
        tipos=["departamentos", "ph", "casas"], tipo_ambiente="dormitorios", valores=[3],
        barrios=["Belgrano", "Vicente Lopez"], precio_max=2000000, moneda="ARS",
    )
    assert _construir_url(crit, 3) == (
        "https://www.zonaprop.com.ar/departamentos-ph-casas-alquiler-belgrano-vicente-lopez"
        "-3-habitaciones-menos-2000000-pesos-orden-publicado-descendente.html"
    )
    props = buscar(crit, max_paginas=1)
    assert props, "buscar devolvio 0 propiedades"
    for p in props:
        assert p.id and p.link.startswith("https://www.zonaprop.com.ar"), p
        assert p.dormitorios == 3, f"{p.id}: dormitorios={p.dormitorios}"
        assert p.ubicaciones, f"{p.id}: sin ubicaciones"
    print(f"OK: {len(props)} propiedades. Ej: {props[0].titulo} | {props[0].moneda} {props[0].precio}"
          f" + exp {props[0].expensas} | dueño={props[0].dueno_directo} | flags={props[0].flags}")


if __name__ == "__main__":
    test_buscar_alquiler()
