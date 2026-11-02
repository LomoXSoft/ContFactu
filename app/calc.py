"""Cálculo de totales como FactuCont: bases agrupadas por tipo de IVA (cualquier tipo y cualquier número de tipos),
descuento general, RE y retención."""
import json
from decimal import Decimal as D, ROUND_HALF_UP, InvalidOperation

C = D("0.01")

def norm(d):
    """Decimal sin ceros de sobra y sin notación exponencial: 10.00 -> 10, 7.50 -> 7.5."""
    d = d.normalize()
    return d.quantize(D(1)) if d == d.to_integral_value() else d

def dec(x):
    if x is None or x == "":
        return D(0)
    return D(str(x))

def r2(x):
    return dec(x).quantize(C, rounding=ROUND_HALF_UP)

def importe_linea(l):
    if l.get("comentario"):
        return D(0)
    return dec(l.get("cantidad")) * dec(l.get("precio")) * (1 - dec(l.get("descuento")) / 100)

def bases_desde_lineas(lineas, descuento_general=0, iva_incluido=False):
    """Devuelve {tipo_iva: base} con dos decimales."""
    grupos = {}
    for l in lineas:
        if l.get("comentario"):
            continue
        iva = norm(dec(l.get("iva")))
        imp = importe_linea(l)
        if iva_incluido:
            imp = imp / (1 + iva / 100)
        grupos[iva] = grupos.get(iva, D(0)) + imp
    f = 1 - dec(descuento_general) / 100
    return {k: r2(v * f) for k, v in grupos.items() if r2(v * f) != 0 or len(grupos) == 1}

def tramos_iva(doc):
    """[(base, iva, re), ...] de un documento. Desde la 0.0.4 el desglose completo va en «desglose_iva» (JSON, sin límite
    de tipos); los documentos anteriores o importados de FactuCont solo tienen base1..3/iva1..3/re1..3."""
    txt = doc.get("desglose_iva") if hasattr(doc, "get") else None
    if txt:
        try:
            return [(dec(b), dec(i), dec(r)) for b, i, r in json.loads(txt)]
        except (ValueError, TypeError, InvalidOperation):
            pass
    return [(dec(doc.get(f"base{i}")), dec(doc.get(f"iva{i}")), dec(doc.get(f"re{i}"))) for i in (1, 2, 3)]

def desglose_json(tramos):
    return json.dumps([[str(b), format(i, "f"), format(r, "f")] for b, i, r in tramos])

def tipo_iva_valido(v):
    """Normaliza un tipo de IVA o de RE escrito por el usuario (admite coma decimal y «%»): 0–100 con dos decimales como máximo.
    Devuelve el texto normalizado ('7.5', '21', '0') o lanza ValueError con un mensaje en español."""
    x = str(v if v is not None else "").strip().replace("%", "").replace(" ", "").replace(",", ".")
    try:
        d = D(x)
    except InvalidOperation:
        raise ValueError(f"Tipo no válido: «{v}». Escriba un número entre 0 y 100 (p. ej. 21 o 7,5).")
    if not d.is_finite() or d < 0 or d > 100:
        raise ValueError(f"Tipo fuera de rango: «{v}». Debe estar entre 0 y 100.")
    if d != d.quantize(C):
        raise ValueError(f"Tipo con demasiados decimales: «{v}». Use como máximo dos (p. ej. 5,25).")
    return format(d.normalize() + 0, "f")

def totales_cabecera(doc):
    """Total de un documento con las bases/tipos de su cabecera."""
    base = cuota_iva = cuota_re = D(0)
    desglose = []
    for b, iva, re in tramos_iva(doc):
        if b == 0:
            continue
        if doc.get("exento"):
            iva = re = D(0)
        ci, cr = r2(b * iva / 100), r2(b * re / 100)
        desglose.append({"base": r2(b), "iva": norm(iva), "cuota_iva": ci, "re": norm(re), "cuota_re": cr})
        base += r2(b); cuota_iva += ci; cuota_re += cr
    ret = r2(base * dec(doc.get("retencion")) / 100)
    return {"desglose": desglose, "base": base, "cuota_iva": cuota_iva, "cuota_re": cuota_re,
            "retencion": ret, "total": base + cuota_iva + cuota_re - ret}

def fmt_eur(x, moneda=False):
    s = f"{r2(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + (" €" if moneda else "")
