# -*- coding: utf-8 -*-
"""
Motor de matching: decide si una Propiedad cumple un Criterio.
Importa el contrato desde models.py (import plano, ver convencion del proyecto).
"""

from __future__ import annotations

from models import Propiedad, Criterio, normalizar_texto


def matchea(prop: Propiedad, crit: Criterio) -> bool:
    """
    Devuelve True si la propiedad cumple TODAS las condiciones del criterio
    que apliquen (AND). Ver motivos_no_match para el detalle de por que no.
    """
    return len(motivos_no_match(prop, crit)) == 0


def motivos_no_match(prop: Propiedad, crit: Criterio) -> list[str]:
    """
    Devuelve la lista de razones por las que la propiedad NO matchea el
    criterio. Lista vacia = matchea.

    SUPUESTO sobre operacion: Propiedad no trae un campo de operacion
    confiable desde el detalle del aviso (parse.py no lo expone), por lo
    que por ahora NO se filtra por crit.operacion. Se asume que todo lo
    que llega ya es de la operacion buscada (venta). Si en el futuro
    parse.py agrega un campo confiable, agregar el filtro aca.
    """
    motivos: list[str] = []

    # ── Barrio ──────────────────────────────────────────────
    # Se compara contra toda la cadena de ubicacion: "Belgrano R > Belgrano",
    # "Olivos > Vicente López" (Zonaprop usa sub-zonas y partidos).
    if crit.barrios:
        barrios_norm = {normalizar_texto(b) for b in crit.barrios}
        ubicaciones = prop.ubicaciones or [prop.barrio]
        if not any(normalizar_texto(u) in barrios_norm for u in ubicaciones):
            motivos.append(
                f"barrio {prop.barrio!r} fuera de criterio {crit.barrios!r}"
            )

    # ── Ambientes o dormitorios (segun tipo_ambiente), con varios valores ──
    if crit.valores:
        attr = "dormitorios" if crit.tipo_ambiente == "dormitorios" else "ambientes"
        valor_prop = getattr(prop, attr)
        if valor_prop is None or valor_prop not in crit.valores:
            motivos.append(
                f"{attr} {valor_prop!r} no está en {crit.valores!r}"
            )

    # ── Precio ──────────────────────────────────────────────
    if crit.precio_min is not None or crit.precio_max is not None:
        precio = precio_en_moneda(prop, crit)
        if precio is None:
            motivos.append(
                f"precio no comparable ({prop.precio!r} {prop.moneda!r} vs {crit.moneda!r})"
            )
        else:
            if crit.incluir_expensas and crit.moneda == "ARS" and prop.expensas:
                precio += prop.expensas
            piso = crit.precio_min if crit.precio_min is not None else 0
            techo = crit.precio_max if crit.precio_max is not None else float("inf")
            if not (piso <= precio <= techo):
                motivos.append(f"precio {precio:.0f} fuera de [{piso}, {techo}]")

    return motivos


def precio_en_moneda(prop: Propiedad, crit: Criterio) -> float | None:
    """Precio del aviso expresado en la moneda del criterio (convierte con usd_ars)."""
    if prop.precio is None:
        return None
    if prop.moneda == crit.moneda:
        return float(prop.precio)
    if crit.usd_ars:
        if prop.moneda == "USD" and crit.moneda == "ARS":
            return prop.precio * crit.usd_ars
        if prop.moneda == "ARS" and crit.moneda == "USD":
            return prop.precio / crit.usd_ars
    return None
