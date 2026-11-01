"""Cálculo de totales como FactuCont: bases agrupadas por tipo de IVA (hasta 3), descuento general, RE y retención."""
from decimal import Decimal as D, ROUND_HALF_UP

C = D("0.01")

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
        iva = dec(l.get("iva")).normalize() + 0
        imp = importe_linea(l)
        if iva_incluido:
            imp = imp / (1 + iva / 100)
        grupos[iva] = grupos.get(iva, D(0)) + imp
    f = 1 - dec(descuento_general) / 100
    return {k: r2(v * f) for k, v in grupos.items() if r2(v * f) != 0 or len(grupos) == 1}

def totales_cabecera(doc):
    """Total de un documento con las bases/tipos de su cabecera."""
    base = cuota_iva = cuota_re = D(0)
    desglose = []
    for i in (1, 2, 3):
        b = dec(doc.get(f"base{i}"))
        if b == 0:
            continue
        iva, re = dec(doc.get(f"iva{i}")), dec(doc.get(f"re{i}"))
        if doc.get("exento"):
            iva = re = D(0)
        ci, cr = r2(b * iva / 100), r2(b * re / 100)
        desglose.append({"base": r2(b), "iva": iva.normalize(), "cuota_iva": ci, "re": re.normalize(), "cuota_re": cr})
        base += r2(b); cuota_iva += ci; cuota_re += cr
    ret = r2(base * dec(doc.get("retencion")) / 100)
    return {"desglose": desglose, "base": base, "cuota_iva": cuota_iva, "cuota_re": cuota_re,
            "retencion": ret, "total": base + cuota_iva + cuota_re - ret}

def fmt_eur(x, moneda=False):
    s = f"{r2(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + (" €" if moneda else "")
