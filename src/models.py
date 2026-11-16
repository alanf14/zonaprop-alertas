# -*- coding: utf-8 -*-
"""
Contratos de datos del motor matcher-zonaprop.
Este archivo define el SHAPE que comparten todos los modulos.
NO agregar logica de negocio aca: solo estructuras + helpers de normalizacion.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Helper compartido de normalizacion (lo usan parse.py y match.py)
# ─────────────────────────────────────────────────────────────
def normalizar_texto(s: str | None) -> str:
    """Minusculas, sin acentos, sin espacios de sobra. Para comparar barrios."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


# ─────────────────────────────────────────────────────────────
# Propiedad: lo que parse.py extrae de un aviso de Zonaprop
# ─────────────────────────────────────────────────────────────
@dataclass
class Propiedad:
    id: str                          # ID del aviso (viene en la URL). Clave para novelty.
    titulo: str
    link: str
    precio: Optional[int] = None     # monto numerico (ej 225000)
    moneda: str = ""                 # "USD" | "ARS" | ""
    barrio: str = ""                 # addressRegion (ej "Belgrano")
    direccion: str = ""              # streetAddress
    ambientes: Optional[int] = None  # numberOfRooms
    dormitorios: Optional[int] = None
    m2: Optional[float] = None       # floorSize.value
    foto: str = ""
    fecha_publicacion: str = ""      # ISO 8601 (ej "2026-05-01T19:59:40Z")
    expensas: Optional[int] = None   # siempre en pesos
    dueno_directo: bool = False      # publisherTypeId "1" en Zonaprop
    tipo: str = ""                   # "Departamentos" | "PH" | "Casas"
    ubicaciones: list[str] = field(default_factory=list)  # ["Belgrano R","Belgrano","Capital Federal",...]
    flags: list[str] = field(default_factory=list)        # green flags: Cochera, Balcón, ...

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────
# Criterio: lo que busca un cliente.
# El filtro de tamanio es flexible: se elige filtrar por "ambientes" o por
# "dormitorios" (tipo_ambiente) y se aceptan VARIOS valores (valores), de modo
# que "3 o 4 ambientes" se representa como tipo_ambiente="ambientes", valores=[3,4].
# ─────────────────────────────────────────────────────────────
@dataclass
class Criterio:
    nombre_cliente: str
    operacion: str = "venta"                    # por ahora siempre "venta"
    tipo_ambiente: str = "ambientes"            # "ambientes" | "dormitorios"
    valores: list[int] = field(default_factory=list)  # ej [3, 4] = "3 o 4"
    barrios: list[str] = field(default_factory=list)  # ej ["Belgrano","Nunez"]
    precio_min: Optional[int] = None
    precio_max: Optional[int] = None
    moneda: str = "USD"                         # "USD" | "ARS"
    tipos: list[str] = field(default_factory=lambda: ["departamentos"])  # + "ph", "casas"
    incluir_expensas: bool = False              # True: el tope es alquiler + expensas
    usd_ars: Optional[float] = None             # cotizacion para comparar avisos en otra moneda
    webhook_env: Optional[str] = None           # variable de entorno con el webhook de ESTE criterio

    @staticmethod
    def from_dict(d: dict) -> "Criterio":
        """Construye un Criterio, migrando el formato viejo si hace falta.

        Retrocompatibilidad: los criterios guardados con el esquema anterior
        (`ambientes` exacto o `ambientes_min`) se convierten a tipo_ambiente +
        valores para no perder las busquedas ya configuradas.
        """
        tipo = d.get("tipo_ambiente")
        valores = d.get("valores")

        if valores is None:  # esquema viejo -> migrar
            if d.get("ambientes") is not None:
                tipo, valores = tipo or "ambientes", [d["ambientes"]]
            elif d.get("ambientes_min") is not None:
                tipo, valores = tipo or "ambientes", [d["ambientes_min"]]
            elif d.get("dormitorios") is not None:
                tipo, valores = tipo or "dormitorios", [d["dormitorios"]]
            else:
                valores = []

        return Criterio(
            nombre_cliente=d.get("nombre_cliente", "sin_nombre"),
            operacion=d.get("operacion", "venta"),
            tipo_ambiente=tipo or "ambientes",
            valores=[int(v) for v in (valores or [])],
            barrios=d.get("barrios", []),
            precio_min=d.get("precio_min"),
            precio_max=d.get("precio_max"),
            moneda=d.get("moneda", "USD"),
            tipos=d.get("tipos") or ["departamentos"],
            incluir_expensas=bool(d.get("incluir_expensas", False)),
            usd_ars=d.get("usd_ars"),
            webhook_env=d.get("webhook_env"),
        )
