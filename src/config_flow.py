# -*- coding: utf-8 -*-
"""
Flujo conversacional para configurar un aviso (criterio de busqueda).

Maquina de estados INDEPENDIENTE de Discord: recibe texto, devuelve texto. Asi se
testea por consola y se reusa maniana en WhatsApp sin tocar esta logica.

Pasos: operacion -> barrios -> tipo (ambientes/dormitorios) -> cantidad (uno o
varios valores, ej "3 o 4") -> precio -> nombre -> confirmar.

Si se precargan datos (ej. de un link de Zonaprop), los pasos ya cubiertos se
saltean y solo se pregunta lo que falta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from models import Criterio

_PASOS = ["operacion", "barrios", "tipo", "cantidad", "precio", "nombre", "confirmar"]

# Preguntas fijas. "cantidad" se genera dinamicamente (depende de tipo).
_PREGUNTAS = {
    "operacion": "¿Qué operación te interesa? (venta / alquiler)",
    "barrios": "¿En qué barrios? Separalos con coma (ej: Belgrano, Núñez, Colegiales)",
    "tipo": "¿Querés filtrar por *ambientes* o por *dormitorios*?",
    "precio": (
        "¿Rango de precio en USD? Escribilo como *mínimo-máximo* "
        "(ej: 170000-230000). Poné *-* si no querés filtrar por precio."
    ),
    "nombre": "¿Con qué nombre guardo esta búsqueda? (ej: el cliente o una referencia)",
}


@dataclass
class Resultado:
    """Lo que devuelve el flujo tras procesar un mensaje del usuario."""
    mensaje: str
    estado: str  # "continua" | "completo" | "cancelado"
    criterio: Criterio | None = None


@dataclass
class FlujoConfig:
    """Estado de una configuracion en progreso para UN usuario."""
    datos: dict = field(default_factory=dict)
    pendientes: list[str] = field(default_factory=lambda: list(_PASOS))

    def __init__(self, datos_previos: dict | None = None):
        self.datos = {}
        self.pendientes = list(_PASOS)
        if datos_previos:
            self._precargar(datos_previos)

    def _precargar(self, previos: dict) -> None:
        """Copia lo que ya vino (ej. de un link) y saltea esos pasos."""
        if previos.get("operacion"):
            self.datos["operacion"] = previos["operacion"]
            self._completar("operacion")
        if previos.get("barrios"):
            self.datos["barrios"] = previos["barrios"]
            self._completar("barrios")
        # Ambientes o dormitorios del link -> definen tipo + valores.
        if previos.get("ambientes") is not None:
            self.datos["tipo_ambiente"] = "ambientes"
            self.datos["valores"] = [previos["ambientes"]]
            self._completar("tipo")
            self._completar("cantidad")
        elif previos.get("dormitorios") is not None:
            self.datos["tipo_ambiente"] = "dormitorios"
            self.datos["valores"] = [previos["dormitorios"]]
            self._completar("tipo")
            self._completar("cantidad")
        if previos.get("precio_min") is not None or previos.get("precio_max") is not None:
            self.datos["precio_min"] = previos.get("precio_min")
            self.datos["precio_max"] = previos.get("precio_max")
            self._completar("precio")
        if previos.get("moneda"):
            self.datos["moneda"] = previos["moneda"]

    def _completar(self, paso: str) -> None:
        if paso in self.pendientes:
            self.pendientes.remove(paso)

    # ── Interfaz publica ────────────────────────────────────────
    def paso_actual(self) -> str:
        return self.pendientes[0]

    def mensaje_inicial(self) -> str:
        """Primer mensaje: reconoce lo precargado y hace la primera pregunta."""
        encabezado = "Vamos a configurar tu aviso. 🏠\n"
        if self.datos:
            encabezado += "Ya reconocí:\n" + self._resumen_datos() + "\n\n"
        return encabezado + self._pregunta_o_confirmacion()

    def recibir(self, texto: str) -> Resultado:
        """Procesa un mensaje del usuario y avanza (o repregunta si es invalido)."""
        texto = (texto or "").strip()

        if texto.lower() in ("cancelar", "cancel", "salir"):
            return Resultado("Listo, cancelé la configuración. 👋", "cancelado")

        paso = self.paso_actual()

        if paso == "confirmar":
            return self._procesar_confirmacion(texto)

        valor, error = _VALIDADORES[paso](texto)
        if error:
            return Resultado(f"⚠️ {error}\n\n{self._texto_pregunta(paso)}", "continua")

        # Guardar el/los valor(es) validado(s) segun el paso.
        if paso == "precio":
            self.datos["precio_min"], self.datos["precio_max"] = valor
            self.datos.setdefault("moneda", "USD")
        elif paso == "tipo":
            self.datos["tipo_ambiente"] = valor
        elif paso == "cantidad":
            self.datos["valores"] = valor
        elif paso == "nombre":
            self.datos["nombre_cliente"] = valor
        else:
            self.datos[paso] = valor
        self._completar(paso)

        return Resultado(self._pregunta_o_confirmacion(), "continua")

    # ── Internos ────────────────────────────────────────────────
    def _texto_pregunta(self, paso: str) -> str:
        """Texto de la pregunta de un paso (la de 'cantidad' es dinamica)."""
        if paso == "cantidad":
            tipo = self.datos.get("tipo_ambiente", "ambientes")
            return (
                f"¿Cuántos {tipo}? Podés poner uno o varios "
                f"(ej: *4* o *3 o 4* si te sirven las dos opciones)."
            )
        return _PREGUNTAS[paso]

    def _pregunta_o_confirmacion(self) -> str:
        if self.paso_actual() == "confirmar":
            return (
                "Confirmá que está bien 👇\n\n"
                + self._resumen_datos()
                + "\n\n¿Guardo esta búsqueda? (sí / no)"
            )
        return self._texto_pregunta(self.paso_actual())

    def _procesar_confirmacion(self, texto: str) -> Resultado:
        t = texto.lower()
        if t in ("si", "sí", "s", "yes", "ok", "dale", "guardar"):
            return Resultado(
                "✅ Guardé tu aviso. Te voy a avisar cuando aparezca algo nuevo que matchee.",
                "completo",
                criterio=self._construir_criterio(),
            )
        if t in ("no", "n", "cancelar"):
            return Resultado("Listo, no guardé nada. 👋", "cancelado")
        return Resultado("Respondé *sí* para guardar o *no* para cancelar.", "continua")

    def _construir_criterio(self) -> Criterio:
        return Criterio(
            nombre_cliente=self.datos.get("nombre_cliente", "sin_nombre"),
            operacion=self.datos.get("operacion", "venta"),
            tipo_ambiente=self.datos.get("tipo_ambiente", "ambientes"),
            valores=self.datos.get("valores", []),
            barrios=self.datos.get("barrios", []),
            precio_min=self.datos.get("precio_min"),
            precio_max=self.datos.get("precio_max"),
            moneda=self.datos.get("moneda", "USD"),
        )

    def _resumen_datos(self) -> str:
        d = self.datos
        precio = "sin filtro de precio"
        if d.get("precio_min") is not None or d.get("precio_max") is not None:
            mn = f"{d['precio_min']:,}" if d.get("precio_min") is not None else "0"
            mx = f"{d['precio_max']:,}" if d.get("precio_max") is not None else "∞"
            precio = f"{d.get('moneda', 'USD')} {mn}–{mx}"
        tamanio = "—"
        if d.get("valores"):
            tipo = d.get("tipo_ambiente", "ambientes")
            tamanio = f"{' o '.join(str(v) for v in d['valores'])} {tipo}"
        partes = [
            f"• Operación: {d.get('operacion', '—')}",
            f"• Barrios: {', '.join(d.get('barrios', [])) or '—'}",
            f"• Tamaño: {tamanio}",
            f"• Precio: {precio}",
        ]
        if d.get("nombre_cliente"):
            partes.append(f"• Nombre: {d['nombre_cliente']}")
        return "\n".join(partes)


# ── Validadores por paso: (texto) -> (valor, error|None) ─────────
def _v_operacion(t: str):
    t = t.strip().lower()
    if t in ("venta", "comprar", "compra"):
        return "venta", None
    if t in ("alquiler", "alquilar", "renta"):
        return "alquiler", None
    return None, "No entendí la operación. Escribí *venta* o *alquiler*."


def _v_barrios(t: str):
    barrios = [b.strip() for b in t.split(",") if b.strip()]
    if not barrios:
        return None, "Necesito al menos un barrio."
    return barrios, None


def _v_tipo(t: str):
    t = t.strip().lower()
    if t in ("ambientes", "ambiente", "amb", "a"):
        return "ambientes", None
    if t in ("dormitorios", "dormitorio", "dorm", "habitaciones", "habitacion", "hab", "d"):
        return "dormitorios", None
    return None, "Escribí *ambientes* o *dormitorios*."


def _v_cantidad(t: str):
    # Acepta uno o varios numeros: "4", "3 o 4", "3,4", "2 3 4".
    numeros = [int(n) for n in re.findall(r"\d+", t)]
    numeros = sorted({n for n in numeros if n > 0})
    if not numeros:
        return None, "Poné al menos un número (ej: 4, o '3 o 4')."
    return numeros, None


def _v_precio(t: str):
    t = t.strip()
    if t in ("-", "", "no", "sin"):
        return (None, None), None
    if "-" not in t:
        return None, "Escribí el precio como *mínimo-máximo* (ej: 170000-230000) o *-* para no filtrar."
    izq, der = (p.strip() for p in t.split("-", 1))
    pmin = pmax = None
    if izq:
        if not izq.isdigit():
            return None, "El mínimo tiene que ser un número (ej: 170000)."
        pmin = int(izq)
    if der:
        if not der.isdigit():
            return None, "El máximo tiene que ser un número (ej: 230000)."
        pmax = int(der)
    if pmin is not None and pmax is not None and pmin > pmax:
        return None, "El mínimo no puede ser mayor que el máximo."
    return (pmin, pmax), None


def _v_nombre(t: str):
    t = t.strip()
    if not t:
        return None, "Necesito un nombre para la búsqueda."
    return t, None


_VALIDADORES = {
    "operacion": _v_operacion,
    "barrios": _v_barrios,
    "tipo": _v_tipo,
    "cantidad": _v_cantidad,
    "precio": _v_precio,
    "nombre": _v_nombre,
}
