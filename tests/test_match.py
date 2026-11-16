# -*- coding: utf-8 -*-
"""
Tests manuales (asserts) de match.py. Correr con:
    python tests/test_match.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import Propiedad, Criterio
from match import matchea, motivos_no_match

crit = Criterio(
    nombre_cliente="cliente_test",
    tipo_ambiente="ambientes",
    valores=[4],
    barrios=["Saavedra", "Nunez", "Belgrano", "Colegiales"],
    precio_min=170000,
    precio_max=230000,
    moneda="USD",
)


def prop(barrio, ambientes, precio, moneda="USD", id="1"):
    return Propiedad(
        id=id,
        titulo="test",
        link="http://test",
        precio=precio,
        moneda=moneda,
        barrio=barrio,
        ambientes=ambientes,
    )


casos = [
    ("4 amb, Belgrano, 225000 USD -> True", prop("Belgrano", 4, 225000), True),
    ("4 amb, Núñez (con acento), 205000 USD -> True", prop("Núñez", 4, 205000), True),
    ("3 amb, Belgrano, 200000 USD -> False (ambientes)", prop("Belgrano", 3, 200000), False),
    ("4 amb, Palermo, 200000 USD -> False (barrio)", prop("Palermo", 4, 200000), False),
    ("4 amb, Belgrano, 300000 USD -> False (precio)", prop("Belgrano", 4, 300000), False),
]

todo_ok = True
for descripcion, p, esperado in casos:
    resultado = matchea(p, crit)
    ok = resultado == esperado
    todo_ok = todo_ok and ok
    estado = "OK" if ok else "FALLO"
    motivos = motivos_no_match(p, crit)
    print(f"[{estado}] {descripcion} -> obtenido={resultado} motivos={motivos}")
    assert ok, f"Caso fallido: {descripcion} (obtenido={resultado}, esperado={esperado})"

assert todo_ok

# ── Alquiler: tope = alquiler + expensas, USD convertido, sub-zonas ──
alq = Criterio(
    nombre_cliente="alq", operacion="alquiler", tipo_ambiente="dormitorios", valores=[3],
    barrios=["Belgrano", "Vicente Lopez"], precio_max=2000000, moneda="ARS",
    incluir_expensas=True, usd_ars=1600,
)


def a(precio, moneda="ARS", expensas=None, ubic=("Belgrano",)):
    return Propiedad(id="x", titulo="t", link="l", precio=precio, moneda=moneda,
                     expensas=expensas, dormitorios=3, barrio=ubic[0], ubicaciones=list(ubic))


casos_alq = [
    ("1.7M + 300k exp = 2M justo", a(1700000, expensas=300000), True),
    ("1.8M + 300k exp = 2.1M", a(1800000, expensas=300000), False),
    ("1.9M sin expensas informadas", a(1900000), True),
    ("USD 1000 (=1.6M) + 300k", a(1000, "USD", 300000), True),
    ("USD 1200 (=1.92M) + 300k", a(1200, "USD", 300000), False),
    ("Belgrano R > Belgrano", a(1500000, ubic=("Belgrano R", "Belgrano", "Capital Federal")), True),
    ("Olivos > Vicente López", a(1500000, ubic=("Olivos", "Vicente López", "GBA Norte")), True),
    ("Palermo Soho", a(1500000, ubic=("Palermo Soho", "Palermo", "Capital Federal")), False),
]
for descripcion, p, esperado in casos_alq:
    obtenido = matchea(p, alq)
    print(f"[{'OK' if obtenido == esperado else 'FALLO'}] {descripcion} -> {obtenido} {motivos_no_match(p, alq)}")
    assert obtenido == esperado, descripcion

print("TEST MATCH OK")
