# -*- coding: utf-8 -*-
"""
Persistencia de IDs ya vistos, usando SQLite (stdlib).
Sirve para que el orquestador (run.py) sepa que avisos ya se notificaron.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from models import Propiedad

_CREAR_TABLA_SQL = """
CREATE TABLE IF NOT EXISTS vistos (
    id TEXT PRIMARY KEY,
    primera_vez TEXT,
    criterio TEXT,
    data_json TEXT
)
"""


def conectar(path: str) -> sqlite3.Connection:
    """
    Abre (o crea) la base SQLite en `path` y garantiza que exista la tabla
    `vistos`. Devuelve la conexion; el llamador es responsable de cerrarla.
    """
    conn = sqlite3.connect(path)
    conn.execute(_CREAR_TABLA_SQL)
    conn.commit()
    return conn


def es_nuevo(conn: sqlite3.Connection, id: str) -> bool:
    """True si el id NO esta registrado todavia en la tabla vistos."""
    cur = conn.execute("SELECT 1 FROM vistos WHERE id = ?", (id,))
    return cur.fetchone() is None


def marcar_visto(conn: sqlite3.Connection, prop: Propiedad, criterio_nombre: str) -> None:
    """
    Registra la propiedad como vista. Idempotente: si el id ya existe,
    no hace nada (INSERT OR IGNORE).
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    data_json = json.dumps(prop.to_dict(), ensure_ascii=False)
    conn.execute(
        "INSERT OR IGNORE INTO vistos (id, primera_vez, criterio, data_json) "
        "VALUES (?, ?, ?, ?)",
        (prop.id, timestamp, criterio_nombre, data_json),
    )
    conn.commit()
