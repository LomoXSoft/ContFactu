"""Exportación a Excel (openpyxl): libros registro de IVA y listados.

Formato pensado para entregar a la gestoría: fila 1 con el título, fila 2 con las cabeceras (filtro y paneles fijos),
una fila por registro, importes como números con dos decimales (no texto), fechas como fechas, y fila de TOTALES.
Los libros siguen las columnas del «Libro registro de IVA» de la AEAT (Orden HAC/773/2019) en lo que ContFactu sabe:
una fila por tipo de IVA de cada factura; total y retención solo en la primera fila de la factura.
"""
import datetime, io
from decimal import Decimal as D
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .calc import dec, r2, totales_cabecera
from . import repo

EUR, PCT, FECHA, TEXTO, ENTERO = "eur", "pct", "fecha", "texto", "entero"
FORMATOS = {EUR: '#,##0.00;-#,##0.00', PCT: '0.00', FECHA: "DD/MM/YYYY", ENTERO: "0"}
ANCHOS = {EUR: 13, PCT: 8, FECHA: 11.5, ENTERO: 8, TEXTO: 14}
_CAB = Font(bold=True, color="FFFFFF")
_RELLENO = PatternFill("solid", fgColor="00407F")
_TOTAL = PatternFill("solid", fgColor="DFF0FF")

def _valor(v, fmt):
    if v is None or v == "":
        return None
    if fmt in (EUR, PCT):
        return r2(v) if fmt == EUR else dec(v).quantize(D("0.01"))
    if fmt == FECHA:
        return datetime.date.fromisoformat(str(v)[:10]) if isinstance(v, str) else v
    if fmt == ENTERO:
        return int(v)
    return v

def hoja(ws, titulo, columnas, filas, totales=True, nota=None, no_sumar=()):
    """columnas: [(clave, cabecera, formato[, ancho])]. Suma en TOTALES las columnas en euros."""
    ws.append([titulo])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([c[1] for c in columnas])
    for celda in ws[2]:
        celda.font, celda.fill = _CAB, _RELLENO
        celda.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[2].height = 45
    for f in filas:
        ws.append([_valor(f.get(c[0]), c[2]) for c in columnas])
    n = len(filas)
    for i, c in enumerate(columnas, 1):
        letra = get_column_letter(i)
        ancho = c[3] if len(c) > 3 else ANCHOS[c[2]]
        palabra = max((len(w) for w in str(c[1]).split()), default=0)       # que ninguna palabra de la cabecera se parta
        ws.column_dimensions[letra].width = max(ancho, palabra * 1.15 + 2)
        if c[2] in FORMATOS:
            for fila in range(3, 3 + n):
                ws.cell(fila, i).number_format = FORMATOS[c[2]]
    if totales and n:
        ws.append([])
        t = ws.max_row + 1
        ws.cell(t, 1, "TOTALES").font = Font(bold=True)
        for i, c in enumerate(columnas, 1):
            ws.cell(t, i).fill = _TOTAL
            if c[2] == EUR and c[0] not in no_sumar:
                celda = ws.cell(t, i, sum((r2(f.get(c[0])) for f in filas if f.get(c[0]) not in (None, "")), D(0)))
                celda.font, celda.number_format = Font(bold=True), FORMATOS[EUR]
                celda.border = Border(top=Side(style="thin"))
    if nota:
        ws.append([])
        ws.append([nota])
        ws.cell(ws.max_row, 1).font = Font(italic=True, color="667085")
    ws.freeze_panes = "A3"
    # al imprimir: apaisado, todas las columnas en el ancho de la página y la cabecera repetida
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.print_title_rows = "2:2"
    if n:
        ws.auto_filter.ref = f"A2:{get_column_letter(len(columnas))}{2 + n}"
    ws.sheet_view.zoomScale = 100
    return ws

def _guardar(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def _cab_empresa(e):
    return f"{e['nombre']} ({e.get('nif') or 'sin NIF'})"

def _trimestre(fecha):
    return f"{(int(fecha[5:7]) - 1) // 3 + 1}T" if fecha else ""

# ------------------------------------------------------------------------------------------------ libros de IVA
COLS_EMITIDAS = [("ejercicio", "Ejercicio", ENTERO), ("periodo", "Periodo", TEXTO, 8), ("tipo_factura", "Tipo de factura", TEXTO, 9),
                 ("fecha", "Fecha expedición", FECHA), ("fecha_operacion", "Fecha operación", FECHA),
                 ("serie", "Serie", TEXTO, 7), ("num", "Número", TEXTO, 10), ("numero", "Nº factura (serie+número)", TEXTO, 12),
                 ("nif", "NIF destinatario", TEXTO, 13), ("nombre", "Nombre destinatario", TEXTO, 32),
                 ("clave", "Clave de operación", TEXTO, 9), ("calificacion", "Calificación de la operación", TEXTO, 11),
                 ("exenta", "Operación exenta", TEXTO, 9), ("total", "Total factura", EUR), ("base", "Base imponible", EUR),
                 ("iva", "Tipo de IVA", PCT), ("cuota_iva", "Cuota IVA repercutida", EUR), ("re", "Tipo recargo eq.", PCT),
                 ("cuota_re", "Cuota recargo eq.", EUR), ("tipo_ret", "Tipo retención IRPF", PCT),
                 ("retencion", "Importe retenido IRPF", EUR), ("rectifica", "Factura rectificada", TEXTO, 12)]
COLS_RECIBIDAS = [("ejercicio", "Ejercicio", ENTERO), ("periodo", "Periodo", TEXTO, 8), ("tipo_factura", "Tipo de factura", TEXTO, 9),
                  ("fecha", "Fecha expedición", FECHA), ("fecha_operacion", "Fecha operación", FECHA), ("fecha", "Fecha recepción", FECHA),
                  ("numero", "Nº de registro", TEXTO, 10), ("num_proveedor", "Nº factura del proveedor", TEXTO, 14),
                  ("nif", "NIF expedidor", TEXTO, 13), ("nombre", "Nombre expedidor", TEXTO, 32),
                  ("clave", "Clave de operación", TEXTO, 9), ("total", "Total factura", EUR), ("base", "Base imponible", EUR),
                  ("iva", "Tipo de IVA", PCT), ("cuota_iva", "Cuota IVA soportada", EUR), ("cuota_iva", "Cuota deducible", EUR),
                  ("re", "Tipo recargo eq.", PCT), ("cuota_re", "Cuota recargo eq.", EUR), ("tipo_ret", "Tipo retención IRPF", PCT),
                  ("retencion", "Importe retenido IRPF", EUR)]

def _filas_libro(con, eid, clase, anio, trimestre):
    filas = repo.libro(con, eid, clase, anio, trimestre)
    ret = {}
    for f in filas:
        if f["documento_id"] not in ret:
            r = con.execute("SELECT retencion FROM documentos WHERE id=?", (f["documento_id"],)).fetchone()
            ret[f["documento_id"]] = r[0] if r else None
        f["ejercicio"] = int(f["fecha"][:4])
        f["periodo"] = _trimestre(f["fecha"])
        f["clave"] = "01"
        f["exenta"] = "Sí" if f["exento"] else ""
        f["calificacion"] = "" if f["exento"] else "S1"
        f["tipo_ret"] = ret[f["documento_id"]] if f["primera"] and dec(ret[f["documento_id"]]) else None
        if not f["primera"]:
            f["total"], f["retencion"] = None, None
        elif not dec(f["retencion"]):
            f["retencion"] = None
        if not dec(f["re"]):
            f["re"], f["cuota_re"] = None, None
    return filas

def libros_iva(con, eid, anio, trimestre=None):
    e = repo.empresa(con, eid)
    periodo = f"{anio}" + (f", {trimestre}.º trimestre" if trimestre else " (año completo)")
    wb = Workbook()
    resumen = {}
    for n, (clase, cols) in enumerate((("emitidas", COLS_EMITIDAS), ("recibidas", COLS_RECIBIDAS))):
        ws = wb.active if n == 0 else wb.create_sheet()
        ws.title = "Emitidas" if clase == "emitidas" else "Recibidas"
        filas = _filas_libro(con, eid, clase, anio, trimestre)
        hoja(ws, f"Libro registro de facturas {clase} — {_cab_empresa(e)} — {periodo}", cols, filas,
             nota=f"Generado por ContFactu el {datetime.date.today():%d/%m/%Y}. Una fila por tipo de IVA; el total y la retención "
                  "figuran en la primera fila de cada factura.")
        resumen[clase] = repo.resumen_libro(repo.libro(con, eid, clase, anio, trimestre))
    ws = wb.create_sheet("Resumen por tipo")
    filas = []
    for clase in ("emitidas", "recibidas"):
        for a in resumen[clase]["por_tipo"]:
            filas.append({"clase": "Repercutido (emitidas)" if clase == "emitidas" else "Soportado (recibidas)", "iva": a["iva"],
                          "base": a["base"], "cuota_iva": a["cuota_iva"], "re": a["re"] if dec(a["re"]) else None,
                          "cuota_re": a["cuota_re"] if dec(a["cuota_re"]) else None})
    hoja(ws, f"Resumen por tipo de IVA — {_cab_empresa(e)} — {periodo}",
         [("clase", "Libro", TEXTO, 24), ("iva", "Tipo de IVA", PCT), ("base", "Base imponible", EUR), ("cuota_iva", "Cuota IVA", EUR),
          ("re", "Tipo recargo eq.", PCT), ("cuota_re", "Cuota recargo eq.", EUR)], filas, totales=False)
    if trimestre:
        _hoja_303(wb, con, eid, anio, trimestre)
    return _guardar(wb)

def _hoja_303(wb, con, eid, anio, trimestre):
    pc = lambda v: format(dec(v).normalize(), "f").replace(".", ",")
    s = repo.resumen_303(con, eid, anio, trimestre)
    filas = []
    for x in s["devengado"]:
        filas.append({"cas": "/".join(x["casillas"]), "concepto": f"IVA devengado al {pc(x['iva'])} %", "base": x["base"], "tipo": x["iva"], "cuota": x["cuota"]})
    for x in s["otros"]:
        filas.append({"cas": "—", "concepto": f"IVA devengado a otro tipo ({pc(x['iva'])} %)", "base": x["base"], "tipo": x["iva"], "cuota": x["cuota"]})
    for x in s["re"]:
        filas.append({"cas": "16-24", "concepto": f"Recargo de equivalencia {pc(x['re'])} %", "base": x["base"], "tipo": x["re"], "cuota": x["cuota"]})
    filas += [{"cas": "27", "concepto": "Total cuota devengada", "cuota": s["c27"]},
              {"cas": "28/29", "concepto": "IVA deducible en operaciones interiores corrientes", "base": s["c28"], "cuota": s["c29"]},
              {"cas": "45", "concepto": "Total a deducir", "cuota": s["c45"]},
              {"cas": "46", "concepto": "Resultado régimen general (27 − 45)", "cuota": s["c46"]},
              {"concepto": "Retenciones practicadas por clientes (orientativo mod. 130)", "cuota": s["ret_emitidas"]},
              {"concepto": "Retenciones de facturas recibidas (orientativo mod. 111/115)", "cuota": s["ret_recibidas"]}]
    hoja(wb.create_sheet("Resumen 303"), f"Resumen aproximado modelo 303 — {anio} {trimestre}T — ORIENTATIVO, revisar con la gestoría",
         [("cas", "Casillas", TEXTO, 9), ("concepto", "Concepto", TEXTO, 58), ("base", "Base", EUR), ("tipo", "Tipo %", PCT),
          ("cuota", "Cuota", EUR)], filas, totales=False)

# ------------------------------------------------------------------------------------------------ listados
def documentos(con, eid, tipo="F", anio="", q=""):
    e = repo.empresa(con, eid)
    sql, args = "SELECT * FROM documentos WHERE empresa_id=? AND tipo=?", [eid, tipo]
    if anio and anio != "todos":
        sql += " AND substr(fecha,1,4)=?"; args.append(anio)
    if q:
        sql += " AND (nombre_f LIKE ? OR numero LIKE ? OR nif LIKE ?)"; args += [f"%{q}%"] * 3
    filas = []
    for d in con.execute(sql + " ORDER BY fecha, serie, numero", args):
        d = dict(d)
        t = totales_cabecera(d)
        vto = con.execute("SELECT MIN(fecha) FROM plazos WHERE documento_id=? AND tipo='' AND CAST(importe AS REAL)-CAST(cobrado AS REAL)<>0",
                          (d["id"],)).fetchone()[0]
        filas.append({"fecha": d["fecha"], "numero": repo.num_visible(d), "nombre": d.get("nombre_f"), "nif": d.get("nif"),
                      "base": t["base"], "cuota_iva": t["cuota_iva"], "cuota_re": t["cuota_re"] or None,
                      "retencion": t["retencion"] or None, "total": t["total"], "pendiente": d.get("pendiente") if tipo in "FAM" else None,
                      "estado": repo.estado_cobro(d) if tipo in "FAM" else "", "vencimiento": vto,
                      "tipos": ", ".join(format(x["iva"], "f").replace(".", ",") + " %" for x in t["desglose"]),
                      "rect": "Sí" if d.get("rect_original_id") else ""})
    nombre_tipo = {"F": "Facturas", "P": "Presupuestos", "A": "Albaranes", "G": "Gastos (facturas recibidas)", "M": "Tiques",
                   "D": "Pedidos"}.get(tipo, "Documentos")
    tercero = "Proveedor" if tipo == "G" else "Cliente"
    cols = [("fecha", "Fecha", FECHA), ("numero", "Número", TEXTO, 11), ("nombre", tercero, TEXTO, 32), ("nif", "NIF", TEXTO, 12),
            ("tipos", "Tipos de IVA", TEXTO, 12), ("base", "Base imponible", EUR), ("cuota_iva", "Cuota IVA", EUR),
            ("cuota_re", "Recargo eq.", EUR), ("retencion", "Retención", EUR), ("total", "Total", EUR)]
    if tipo in "FAM":
        cols += [("pendiente", "Pendiente", EUR), ("estado", "Estado", TEXTO, 10), ("vencimiento", "Próximo vencimiento", FECHA)]
    if tipo == "F":
        cols.append(("rect", "Rectificativa", TEXTO, 10))
    wb = Workbook()
    ws = wb.active; ws.title = nombre_tipo[:31]
    hoja(ws, f"{nombre_tipo} — {_cab_empresa(e)}" + (f" — {anio}" if anio and anio != "todos" else "") + (f" — búsqueda «{q}»" if q else ""),
         cols, filas)
    return _guardar(wb)

def terceros(con, eid, tabla):
    e = repo.empresa(con, eid)
    filas = [dict(r) for r in con.execute(f"SELECT * FROM {tabla} WHERE empresa_id=? ORDER BY codigo", (eid,))]
    for f in filas:
        f["re"] = "Sí" if f.get("recargo") else ""
        f["ret"] = f.get("retencion") if dec(f.get("retencion")) else None
    cols = [("codigo", "Código", TEXTO, 9), ("nombre", "Nombre", TEXTO, 30), ("nombre_f", "Nombre fiscal", TEXTO, 30), ("nif", "NIF", TEXTO, 12),
            ("direccion", "Dirección", TEXTO, 30), ("ciudad", "Población", TEXTO, 20), ("telefono", "Teléfono", TEXTO, 12),
            ("movil", "Móvil", TEXTO, 12), ("email", "Correo electrónico", TEXTO, 26), ("contacto", "Contacto", TEXTO, 18),
            ("forma_pago", "Forma de pago", TEXTO, 16), ("dias_pago", "Días de pago", TEXTO, 10)]
    cols += [("re", "Recargo eq.", TEXTO, 9)] if tabla == "clientes" else [("ret", "Retención %", PCT)]
    wb = Workbook()
    ws = wb.active; ws.title = tabla.capitalize()
    hoja(ws, f"{tabla.capitalize()} — {_cab_empresa(e)} — {len(filas)} fichas", cols, filas, totales=False)
    return _guardar(wb)

def pendientes(con, eid):
    e = repo.empresa(con, eid)
    hoy = repo.hoy()
    filas = []
    for d in repo.pendientes(con, eid):
        vtos = d["vencimientos"] or [{"fecha": d["fecha"], "importe": d["pendiente"], "cobrado": "0", "concepto": ""}]
        for p in vtos:
            imp = dec(p["importe"]) - dec(p.get("cobrado"))
            dias = (datetime.date.fromisoformat(hoy) - datetime.date.fromisoformat(p["fecha"])).days if p.get("fecha") else None
            filas.append({"documento": ("Albarán " if d["tipo"] == "A" else "") + repo.num_visible(d), "fecha": d["fecha"],
                          "nombre": d.get("nombre_f"), "nif": d.get("nif"), "vencimiento": p.get("fecha"),
                          "dias": dias if dias and dias > 0 else None, "importe": imp, "total": d["total"],
                          "estado": "vencido" if p.get("fecha") and p["fecha"] < hoy else "pendiente", "forma": d.get("forma_pago")})
    filas.sort(key=lambda f: (f["vencimiento"] or "", f["documento"]))
    wb = Workbook()
    ws = wb.active; ws.title = "Cobros pendientes"
    hoja(ws, f"Cobros pendientes — {_cab_empresa(e)} — a {datetime.date.today():%d/%m/%Y}",
         [("vencimiento", "Vencimiento", FECHA), ("estado", "Estado", TEXTO, 10), ("dias", "Días vencido", ENTERO, 9),
          ("documento", "Documento", TEXTO, 13), ("fecha", "Fecha documento", FECHA), ("nombre", "Cliente", TEXTO, 32),
          ("nif", "NIF", TEXTO, 12), ("forma", "Forma de pago", TEXTO, 16), ("importe", "Importe pendiente", EUR),
          ("total", "Total documento", EUR)], filas,
         nota="El total del documento se repite en cada vencimiento; por eso no se suma.", no_sumar=("total",))
    return _guardar(wb)
