# -*- coding: utf-8 -*-
"""
Gestion del archivo criterios.json (la lista de busquedas activas).

Lo usan el bot de Discord (para agregar/listar/borrar avisos) y run.py (para
leer que buscar). Formato del archivo:

    {"criterios": [ {criterio...}, {criterio...} ]}

Cada criterio guarda los campos de models.Criterio + metadata opcional
(creado_por, creado_en) que Criterio.from_dict ignora sin romper.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from models import Criterio


def _cargar_raw(path: str | Path) -> dict:
    """Lee el JSON completo; si no existe, devuelve estructura vacia."""
    path = Path(path)
    if not path.exists():
        return {"criterios": []}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "criterios" not in data or not isinstance(data["criterios"], list):
        data["criterios"] = []
    return data


def _guardar_raw(path: str | Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def listar(path: str | Path) -> list[dict]:
    """Devuelve la lista de criterios (como dicts crudos del JSON)."""
    return _cargar_raw(path).get("criterios", [])


def agregar(path: str | Path, criterio: Criterio, creado_por: str | None = None) -> dict:
    """Agrega un criterio al archivo y lo persiste. Devuelve el dict guardado.

    `creado_por`: identificador opcional (ej. usuario de Discord) para saber
    de quien es la busqueda. Se guarda como metadata sin afectar el matcheo.
    """
    data = _cargar_raw(path)
    registro = {
        "nombre_cliente": criterio.nombre_cliente,
        "operacion": criterio.operacion,
        "tipo_ambiente": criterio.tipo_ambiente,
        "valores": criterio.valores,
        "barrios": criterio.barrios,
        "precio_min": criterio.precio_min,
        "precio_max": criterio.precio_max,
        "moneda": criterio.moneda,
        "creado_por": creado_por,
        "creado_en": datetime.now(timezone.utc).isoformat(),
    }
    data["criterios"].append(registro)
    _guardar_raw(path, data)
    return registro


def borrar_por_nombre(path: str | Path, nombre_cliente: str) -> int:
    """Borra los criterios cuyo nombre_cliente coincide. Devuelve cuantos borro."""
    data = _cargar_raw(path)
    antes = len(data["criterios"])
    data["criterios"] = [
        c for c in data["criterios"]
        if c.get("nombre_cliente", "").strip().lower() != nombre_cliente.strip().lower()
    ]
    borrados = antes - len(data["criterios"])
    if borrados:
        _guardar_raw(path, data)
    return borrados
