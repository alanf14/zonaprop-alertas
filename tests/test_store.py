# -*- coding: utf-8 -*-
"""
Tests manuales (asserts) de store.py. Correr con:
    python tests/test_store.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import Propiedad
from store import conectar, es_nuevo, marcar_visto

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "test_tmp.db")

# Borrar DB temporal si quedo de una corrida anterior
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = conectar(DB_PATH)

prop = Propiedad(
    id="abc123",
    titulo="Depto test",
    link="http://test",
    precio=200000,
    moneda="USD",
    barrio="Belgrano",
    ambientes=4,
)

assert es_nuevo(conn, prop.id) is True
print("[OK] es_nuevo antes de marcar -> True")

marcar_visto(conn, prop, "cliente_test")
assert es_nuevo(conn, prop.id) is False
print("[OK] es_nuevo despues de marcar -> False")

# Marcar dos veces el mismo id no debe romper (idempotencia)
marcar_visto(conn, prop, "cliente_test")
cur = conn.execute("SELECT COUNT(*) FROM vistos WHERE id = ?", (prop.id,))
cantidad = cur.fetchone()[0]
assert cantidad == 1, f"Se esperaba 1 fila, hay {cantidad}"
print("[OK] marcar_visto dos veces no duplica filas")

conn.close()

# Limpieza
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

print("TEST STORE OK")
