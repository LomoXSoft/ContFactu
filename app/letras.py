"""Importe en letra (castellano) para recibos."""
from decimal import Decimal, ROUND_HALF_UP

_U = ["", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ", "ONCE", "DOCE", "TRECE",
      "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE", "VEINTIUNO", "VEINTIDÓS",
      "VEINTITRÉS", "VEINTICUATRO", "VEINTICINCO", "VEINTISÉIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE"]
_D = ["", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
_C = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS",
      "OCHOCIENTOS", "NOVECIENTOS"]

def _menor_mil(n):
    if n == 0: return ""
    if n == 100: return "CIEN"
    c, r = divmod(n, 100)
    if r < 30: resto = _U[r]
    else:
        d, u = divmod(r, 10)
        resto = _D[d] + (" Y " + _U[u] if u else "")
    return (_C[c] + " " + resto).strip()

def entero_a_letras(n):
    if n == 0: return "CERO"
    partes = []
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    if millones:
        partes.append("UN MILLÓN" if millones == 1 else entero_a_letras(millones) + " MILLONES")
    if miles:
        partes.append("MIL" if miles == 1 else _menor_mil(miles) + " MIL")
    if unidades:
        partes.append(_menor_mil(unidades))
    txt = " ".join(partes)
    return txt.replace("VEINTIUNO MIL", "VEINTIÚN MIL").replace("UNO MIL", "UN MIL").replace("UNO MILLONES", "UN MILLONES")

def importe_a_letras(x):
    x = Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    neg = x < 0
    x = abs(x)
    e, c = int(x), int((x - int(x)) * 100)
    txt = entero_a_letras(e) + (" EURO" if e == 1 else " EUROS")
    if c:
        txt += " CON " + entero_a_letras(c) + (" CÉNTIMO" if c == 1 else " CÉNTIMOS")
    txt = txt.replace("VEINTIUNO EURO", "VEINTIÚN EURO").replace("VEINTIUNO CÉNTIMO", "VEINTIÚN CÉNTIMO")
    return ("MENOS " if neg else "") + txt.replace("UNO EURO", "UN EURO").replace("UNO EUROS", "UN EUROS").replace("UNO CÉNTIMO", "UN CÉNTIMO")
