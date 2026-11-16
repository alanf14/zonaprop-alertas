# -*- coding: utf-8 -*-
"""
Dashboard local read-only, centrado en LEADS.

Pantalla 1: tabla de leads.  Clic en un lead -> su pagina con las busquedas
(criterios) que necesita, la cantidad de propiedades avisadas y los links.

Datos: criterios.json (busquedas) + salidas/*.json (propiedades avisadas).
Un criterio se asocia a un lead con el campo "lead" (y "contacto" opcional) en
criterios.json; si no lo tiene, se usa su nombre_cliente como lead.

Uso:  python src/dashboard.py   ->  genera y abre dashboard.html.
Se regenera cada corrida (para refrescar). ponytail: HTML estatico + JS minimo
para cambiar de vista; no hay servidor hasta que haga falta.
"""

from __future__ import annotations

import html
import json
import webbrowser
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CRITERIOS = RAIZ / "criterios.json"
SALIDAS = RAIZ / "salidas"
SALIDA_HTML = RAIZ / "dashboard.html"


def _cargar_criterios() -> list[dict]:
    if not CRITERIOS.exists():
        return []
    return json.loads(CRITERIOS.read_text(encoding="utf-8")).get("criterios", [])


def _avisadas_por_busqueda() -> dict[str, list[dict]]:
    """Agrega salidas/*.json -> {nombre_busqueda: [props...]}, deduplicadas por id."""
    por_nombre: dict[str, dict[str, dict]] = defaultdict(dict)
    for archivo in sorted(SALIDAS.glob("nuevas_*.json")):
        try:
            data = json.loads(archivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for nombre, props in data.items():
            for p in props:
                por_nombre[nombre][p.get("id") or id(p)] = p
    return {k: list(v.values()) for k, v in por_nombre.items()}


def agrupar_por_lead() -> list[dict]:
    """[{lead, contacto, busquedas:[{crit, props}], total_avisadas}] ordenado."""
    avisadas = _avisadas_por_busqueda()
    leads: dict[str, dict] = {}
    for c in _cargar_criterios():
        nombre_lead = c.get("lead") or c.get("nombre_cliente", "(sin lead)")
        props = avisadas.get(c.get("nombre_cliente", ""), [])
        lead = leads.setdefault(nombre_lead, {"lead": nombre_lead, "contacto": "", "busquedas": []})
        if c.get("contacto") and not lead["contacto"]:
            lead["contacto"] = c["contacto"]
        lead["busquedas"].append({"crit": c, "props": props})
    salida = list(leads.values())
    for l in salida:
        l["total_avisadas"] = sum(len(b["props"]) for b in l["busquedas"])
    return salida


# ── Helpers de formato ───────────────────────────────────────────
def _tamanio(p: dict) -> str:
    partes = []
    if p.get("ambientes") is not None:
        partes.append(f"{p['ambientes']} amb")
    if p.get("dormitorios") is not None:
        partes.append(f"{p['dormitorios']} dorm")
    return " · ".join(partes) or "—"


def _precio(p: dict) -> str:
    if p.get("precio") is None:
        return "consultar"
    return f"{p.get('moneda', '')} {p['precio']:,}".strip()


def _filtros(c: dict) -> str:
    valores = c.get("valores") or ([c["ambientes"]] if c.get("ambientes") else [])
    tipo = c.get("tipo_ambiente", "ambientes")
    tam = f"{' o '.join(map(str, valores))} {tipo}" if valores else "cualquier tamaño"
    precio = "sin filtro"
    if c.get("precio_min") is not None or c.get("precio_max") is not None:
        precio = f"{c.get('moneda', 'USD')} {c.get('precio_min') or 0}–{c.get('precio_max') or '∞'}"
    barrios = ", ".join(c.get("barrios", []))
    return f"{c.get('operacion', '—')} · {tam} · {precio} · {barrios}"


# ── Render ───────────────────────────────────────────────────────
def _card(p: dict) -> str:
    e = html.escape
    foto = p.get("foto") or ""
    img = f'<img src="{e(foto)}" loading="lazy">' if foto else '<div class="noimg">sin foto</div>'
    return (
        f'<a class="card" href="{e(p.get("link",""))}" target="_blank">{img}'
        f'<div class="cbody"><div class="ctit">{e(p.get("titulo","(sin título)"))}</div>'
        f'<div class="cprecio">{e(_precio(p))}</div>'
        f'<div class="cmeta">{e(p.get("barrio","") or "")} · {e(_tamanio(p))}</div></div></a>'
    )


def _fila_lead(i: int, l: dict) -> str:
    e = html.escape
    return (
        f'<tr onclick="show({i})"><td><b>{e(l["lead"])}</b></td>'
        f'<td>{e(l["contacto"] or "—")}</td>'
        f'<td class="num">{len(l["busquedas"])}</td>'
        f'<td class="num">{l["total_avisadas"]}</td></tr>'
    )


def _detalle_lead(i: int, l: dict) -> str:
    e = html.escape
    bloques = []
    for b in l["busquedas"]:
        cards = "".join(_card(p) for p in b["props"]) or '<p class="muted">Todavía sin avisos.</p>'
        bloques.append(
            f'<h3>{e(b["crit"].get("nombre_cliente","(sin nombre)"))} '
            f'<span class="muted">({len(b["props"])} avisadas)</span></h3>'
            f'<div class="meta">{e(_filtros(b["crit"]))}</div>'
            f'<div class="grid">{cards}</div>'
        )
    return (
        f'<div class="detalle" id="lead{i}" hidden>'
        f'<button class="volver" onclick="volver()">← Volver a leads</button>'
        f'<h2>{e(l["lead"])}</h2>'
        f'<div class="meta">Contacto: {e(l["contacto"] or "—")} · '
        f'{len(l["busquedas"])} búsqueda(s) · {l["total_avisadas"]} propiedad(es) avisada(s)</div>'
        f'{"".join(bloques)}</div>'
    )


def generar() -> Path:
    leads = agrupar_por_lead()
    filas = "".join(_fila_lead(i, l) for i, l in enumerate(leads)) or \
        '<tr><td colspan="4" class="muted">No hay leads/búsquedas todavía.</td></tr>'
    detalles = "".join(_detalle_lead(i, l) for i, l in enumerate(leads))

    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard — Leads y avisos</title>
<style>
  body{{font-family:system-ui,sans-serif;margin:0;background:#0f1115;color:#e8eaed}}
  header{{padding:18px 24px;border-bottom:1px solid #262a33}}
  header h1{{margin:0;font-size:20px}} .muted{{color:#8a90a0}}
  .wrap{{padding:20px 24px}}
  table{{width:100%;border-collapse:collapse}}
  th,td{{text-align:left;padding:12px 14px;border-bottom:1px solid #1c1f27}}
  th{{color:#a9b0c0;font-size:13px;text-transform:uppercase;letter-spacing:.04em}}
  tbody tr{{cursor:pointer}} tbody tr:hover{{background:#171a21}}
  td.num,th.num{{text-align:right;width:120px}}
  .detalle{{padding:20px 24px}}
  .volver{{background:#233;color:#cfe;border:0;padding:8px 14px;border-radius:8px;cursor:pointer;font-size:14px;margin-bottom:12px}}
  .detalle h2{{margin:.2em 0}} .detalle h3{{margin:1.2em 0 .2em;font-size:16px}}
  .meta{{color:#a9b0c0;font-size:14px;margin-bottom:10px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}}
  .card{{background:#171a21;border:1px solid #262a33;border-radius:10px;overflow:hidden;text-decoration:none;color:inherit;display:flex;flex-direction:column}}
  .card img,.noimg{{width:100%;height:150px;object-fit:cover;background:#222}}
  .noimg{{display:flex;align-items:center;justify-content:center;color:#666;font-size:13px}}
  .cbody{{padding:10px}} .ctit{{font-size:14px;font-weight:600;line-height:1.3;margin-bottom:6px}}
  .cprecio{{color:#4ade80;font-weight:700}} .cmeta{{color:#a9b0c0;font-size:13px;margin-top:2px}}
</style></head><body>
<header><h1>🏠 Dashboard — Leads y avisos</h1>
<span class="muted">{len(leads)} lead(s)</span></header>
<div class="wrap" id="lista">
  <table><thead><tr><th>Lead</th><th>Contacto</th><th class="num">Búsquedas</th><th class="num">Avisadas</th></tr></thead>
  <tbody>{filas}</tbody></table>
</div>
{detalles}
<script>
function show(i){{document.getElementById('lista').hidden=true;
  document.querySelectorAll('.detalle').forEach(d=>d.hidden=true);
  document.getElementById('lead'+i).hidden=false;window.scrollTo(0,0);}}
function volver(){{document.getElementById('lista').hidden=false;
  document.querySelectorAll('.detalle').forEach(d=>d.hidden=true);}}
</script>
</body></html>"""
    SALIDA_HTML.write_text(doc, encoding="utf-8")
    return SALIDA_HTML


if __name__ == "__main__":
    ruta = generar()
    print(f"Dashboard generado: {ruta}")
    webbrowser.open(ruta.as_uri())
