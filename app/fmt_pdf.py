"""Intérprete de los diseños .fmt de FactuCont (Editor de formatos de Binarema, v2.0) -> PDF con ReportLab.

Formato .fmt (INI, cp1252, medidas en mm con coma decimal):
  [Documento]  PapelAncho/PapelAlto, márgenes Superior/Inferior/Izquierdo/Derecho
  [Banda0] cabecera (arriba), [Banda1] línea de detalle (se repite), [Banda2] pie (abajo de la página)
  [ObjetoN] Banda, PosX, PosY, TamX, TamY, Tipo:
     0 texto fijo (Texto=..., termina en '.'), 1 dato de sistema (3=nº página, 4=título del documento),
     2 campo de cabecera (F>campo documento, E>empresa, C>cliente, o calculados BASE_DOC, IVA_DOC, TOTAL_DOC, ..._PLAZ)
     4 figura (rectángulo) con RellenoColor/BordeColor, 5 campo de línea (CODIGO, CONCEPTO, CANTIDAD...)
  Colores en formato Windows (0x00BBGGRR). Estilo: bits 1 negrita, 2 cursiva, 4 subrayado.
  Alineación: 0 izquierda, 1 derecha, 2 centrada.
"""
import configparser, io
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import Color
from reportlab.pdfbase.pdfmetrics import stringWidth
from .calc import dec, r2, fmt_eur, importe_linea, totales_cabecera

TITULOS = {"F": "FACTURA", "A": "ALBARÁN", "P": "PRESUPUESTO", "G": "GASTO", "M": "TIQUE", "D": "PEDIDO"}
PT = 0.3528  # mm por punto

def parse_fmt(texto):
    cp = configparser.RawConfigParser(strict=False)
    cp.optionxform = str
    cp.read_string(texto)
    def num(sec, k, d=0.0):
        try:
            return float(cp.get(sec, k).replace(",", "."))
        except Exception:
            return d
    doc = {k: num("Documento", k) for k in ("PapelAncho", "PapelAlto", "Superior", "Inferior", "Izquierdo", "Derecho")}
    doc["PapelAncho"] = doc["PapelAncho"] or 210; doc["PapelAlto"] = doc["PapelAlto"] or 297
    bandas = {i: num(f"Banda{i}", "Alto") for i in range(3)}
    objs = []
    for s in cp.sections():
        if s.startswith("Objeto"):
            o = {k: v for k, v in cp.items(s)}
            for k in ("PosX", "PosY", "TamX", "TamY"):
                o[k] = num(s, k)
            o["_n"] = int(s[6:])
            objs.append(o)
    objs.sort(key=lambda o: o["_n"])
    return doc, bandas, objs

def win_color(v, default=0):
    try:
        v = int(v)
    except Exception:
        v = default
    return Color((v & 0xFF) / 255, ((v >> 8) & 0xFF) / 255, ((v >> 16) & 0xFF) / 255)

def font_for(o):
    nombre = (o.get("FNombre") or "Arial").lower()
    est = int(o.get("Estilo") or 0)
    b, i = est & 1, est & 2
    if "times" in nombre:
        return {(0, 0): "Times-Roman", (1, 0): "Times-Bold", (0, 2): "Times-Italic", (1, 2): "Times-BoldItalic"}[(b, i)]
    if "courier" in nombre:
        return {(0, 0): "Courier", (1, 0): "Courier-Bold", (0, 2): "Courier-Oblique", (1, 2): "Courier-BoldOblique"}[(b, i)]
    return {(0, 0): "Helvetica", (1, 0): "Helvetica-Bold", (0, 2): "Helvetica-Oblique", (1, 2): "Helvetica-BoldOblique"}[(b, i)]

def _fecha(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}" if iso else ""

def _cant(v):
    if v in (None, ""):
        return ""
    s = f"{dec(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s[:-3] if s.endswith(",00") else s

def _pct(v):
    if v in (None, "") or dec(v) == 0:
        return ""
    return _cant(v)

class Contexto:
    def __init__(self, empresa, doc, lineas, plazos, cliente=None):
        self.e, self.d, self.lineas, self.plazos, self.c = empresa, doc, lineas, plazos, cliente or {}
        self.tot = totales_cabecera(doc)

    def campo_cabecera(self, campo, moneda=False):
        """Devuelve lista de líneas de texto."""
        d, t = self.d, self.tot
        if campo.startswith("F>"):
            k = campo[2:]
            m = {"NUMERO": (d.get("serie") or "").strip() + (d.get("numero") or ""), "FECHA": _fecha(d.get("fecha")), "NOMBREF": d.get("nombre_f"),
                 "DIRECCIONF": d.get("direccion_f"), "CIUDADF": d.get("ciudad_f"), "CIF": d.get("nif"),
                 "FORMAPAGO": d.get("forma_pago"), "DOMICILIA": d.get("domiciliacion"), "CCC": d.get("ccc"),
                 "DESCUENTO": _pct(d.get("descuento")), "FECHAOPERA": _fecha(d.get("fecha_operacion")),
                 "DIASPAGO": d.get("dias_pago"), "BIC": d.get("bic"), "RETENCION": _pct(d.get("retencion"))}
            return [m.get(k) or ""]
        if campo.startswith("E>"):
            k = campo[2:]
            m = {"NOMBRE": self.e.get("nombre"), "DIRECCION": self.e.get("direccion"), "CIUDAD": self.e.get("ciudad"),
                 "CIF": self.e.get("nif"), "ACTIVIDAD": self.e.get("actividad")}
            return [m.get(k) or ""]
        if campo.startswith("C>"):
            return [self.c.get(campo[2:].lower()) or ""]
        des = t["desglose"]
        if campo == "BASE_DOC":
            return [fmt_eur(x["base"], moneda) for x in des]
        if campo == "%IVA_DOC":
            return [_cant(x["iva"]) for x in des]
        if campo == "IVA_DOC":
            return [fmt_eur(x["cuota_iva"], moneda) for x in des]
        if campo == "%RE_DOC":
            return [_pct(x["re"]) for x in des]
        if campo == "RE_DOC":
            return [fmt_eur(x["cuota_re"], moneda) if x["cuota_re"] else "" for x in des]
        if campo == "TOTAL_DOC":
            return [fmt_eur(t["total"], moneda)]
        if campo == "RETENIDO_DOC":
            return [fmt_eur(t["retencion"], moneda) if t["retencion"] else ""]
        vto = [p for p in self.plazos if (p.get("tipo") or "") in ("", "A") and dec(p.get("importe")) != 0]
        if campo == "FECH_PLAZ":
            return [_fecha(p["fecha"]) for p in vto]
        if campo == "CONC_PLAZ":
            return [p["concepto"] or "" for p in vto]
        if campo == "IMPO_PLAZ":
            return [fmt_eur(p["importe"], moneda) for p in vto]
        return [""]

    @staticmethod
    def campo_linea(l, campo, moneda=False):
        if l.get("comentario") and campo != "CONCEPTO":
            return ""
        if campo == "CODIGO": return l.get("codigo") or ""
        if campo == "CONCEPTO": return l.get("concepto") or ""
        if campo == "CANTIDAD": return _cant(l.get("cantidad"))
        if campo == "PRECIO": return fmt_eur(l.get("precio"), moneda)
        if campo == "DESCUENTO": return _pct(l.get("descuento"))
        if campo == "IVA": return _cant(l.get("iva"))
        if campo == "IMPORTE": return fmt_eur(importe_linea(l), moneda)
        return ""

def _wrap(texto, font, size, ancho_pt):
    palabras, lineas, actual = texto.split(" "), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip() if actual else p
        if stringWidth(prueba, font, size) <= ancho_pt or not actual:
            actual = prueba
        else:
            lineas.append(actual); actual = p
    lineas.append(actual)
    return lineas

def _num(o, k, d):
    try:
        return float((o.get(k) or d).replace(",", "."))
    except Exception:
        return float(d)

def _color(v, default=0):
    try:
        v = int(v)
    except Exception:
        v = default
    if v < 0:  # colores de sistema de Windows (0x80000008 = texto de ventana...): negro, salvo fondos -> blanco
        return win_color(0xFFFFFF if (v & 0xFF) in (5, 15) else 0)
    return win_color(v)

class Lienzo:
    """Dibuja objetos .fmt sobre un canvas de ReportLab (coordenadas en mm desde arriba-izquierda)."""
    def __init__(self, c, alto_mm):
        self.c, self.H = c, alto_mm

    def Y(self, y_mm):
        return (self.H - y_mm) * mm

    def texto(self, o, x0, y0, lineas_txt, ajustar=False):
        c = self.c
        font, size = font_for(o), _num(o, "FTamaño", _num(o, "FTamano", "10"))
        al = int(o.get("Alineación") or o.get("Alineacion") or 0)
        x, w = (x0 + o["PosX"]) * mm, o["TamX"] * mm
        if ajustar:  # reducir la letra hasta que quepa (p. ej. "FACTURA RECTIFICATIVA" en la caja del título)
            ancho = max((stringWidth(str(t), font, size) for t in lineas_txt), default=0)
            if ancho > w > 0:
                size = max(size * w / ancho * 0.98, 5)
        c.setFillColor(_color(o.get("FColor"), 0)); c.setFont(font, size)
        lh = size * 1.15
        y = self.Y(y0 + o["PosY"]) - size * 0.95
        for t in lineas_txt:
            t = str(t)
            if al == 1: c.drawRightString(x + w, y, t)
            elif al == 2: c.drawCentredString(x + w / 2, y, t)
            else: c.drawString(x, y, t)
            if int(o.get("Estilo") or 0) & 4:
                tw = stringWidth(t, font, size); xs = x if al == 0 else (x + w - tw if al == 1 else x + (w - tw) / 2)
                c.setLineWidth(size / 18); c.setStrokeColor(_color(o.get("FColor"), 0)); c.line(xs, y - 1.5, xs + tw, y - 1.5)
            y -= lh

    def figura(self, o, x0, y0):
        c = self.c
        x, y, w, h = (x0 + o["PosX"]) * mm, self.Y(y0 + o["PosY"] + o["TamY"]), o["TamX"] * mm, o["TamY"] * mm
        relleno = o.get("RellenoTipo", "0") == "0"
        c.setFillColor(_color(o.get("RellenoColor"), 0xFFFFFF))
        c.setStrokeColor(_color(o.get("BordeColor"), 0))
        c.setLineWidth(max(float(o.get("BordeGrosor") or 0), 0.25) * 0.5)
        tf = o.get("TipoFigura", "0")
        if tf == "2":
            c.ellipse(x, y, x + w, y + h, stroke=1, fill=int(relleno))
        elif o.get("EsqRedondeadas") == "1" and tf == "1":
            c.roundRect(x, y, w, h, 2 * mm, stroke=1, fill=int(relleno))
        else:
            c.rect(x, y, w, h, stroke=1, fill=int(relleno))

def titulo_documento(doc):
    if doc.get("tipo") == "F" and doc.get("rect_original_id"):
        return "FACTURA RECTIFICATIVA"
    return TITULOS.get(doc.get("tipo"), "DOCUMENTO")

def render_pdf(fmt_texto, empresa, doc, lineas, plazos, cliente=None, salida=None, lineas_previas=None):
    """lineas_previas: líneas de comentario que se imprimen antes del detalle (p. ej. la referencia de la rectificativa)."""
    fdoc, bandas, objs = parse_fmt(fmt_texto)
    W, H = fdoc["PapelAncho"], fdoc["PapelAlto"]
    ml, mt, mb = fdoc["Izquierdo"], fdoc["Superior"], fdoc["Inferior"]
    ctx = Contexto(empresa, doc, lineas, plazos, cliente)
    titulo = titulo_documento(doc)
    lineas = [{"concepto": t, "comentario": 1} for t in (lineas_previas or [])] + list(lineas)
    buf = salida or io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W * mm, H * mm))
    c.setTitle(f"{titulo} {doc.get('serie') or ''}{doc.get('numero')}")
    c.setAuthor(empresa.get("nombre") or "")
    lz = Lienzo(c, H)
    texto, figura = lz.texto, lz.figura

    def dibujar_banda(n, x0, y0, pagina, linea=None):
        for o in objs:
            if int(o.get("Banda", -1)) != n:
                continue
            tipo = o.get("Tipo")
            if tipo == "4":
                figura(o, x0, y0)
            elif tipo == "0":
                t = o.get("Texto", "")
                texto(o, x0, y0, [t[:-1] if t.endswith(".") else t])
            elif tipo == "1":
                s = o.get("Sistema")
                v = {"3": str(pagina), "4": titulo}.get(s, "")
                texto(o, x0, y0, [v], ajustar=(s == "4"))
            elif tipo == "2":
                texto(o, x0, y0, ctx.campo_cabecera(o.get("Campo", ""), o.get("MostrarMoneda") == "1"))
            elif tipo == "5" and linea is not None:
                campo = o.get("Campo", "")
                v = ctx.campo_linea(linea, campo, o.get("MostrarMoneda") == "1")
                if campo == "CONCEPTO":
                    size = float((o.get("FTamaño") or "9").replace(",", "."))
                    texto(o, x0, y0, _wrap(v, font_for(o), size, o["TamX"] * mm))
                else:
                    texto(o, x0, y0, [v])

    # alto que ocupa cada línea (CONCEPTO puede ocupar varias)
    oc = next((o for o in objs if o.get("Tipo") == "5" and o.get("Campo") == "CONCEPTO"), None)
    def alto_linea(l):
        if not oc:
            return bandas[1]
        size = float((oc.get("FTamaño") or "9").replace(",", "."))
        n = len(_wrap(l.get("concepto") or "", font_for(oc), size, oc["TamX"] * mm))
        return bandas[1] + (n - 1) * size * 1.15 * PT

    inicio_lineas = mt + bandas[0]
    inicio_pie = H - mb - bandas[2]
    pagina, y = 1, inicio_lineas
    dibujar_banda(0, ml, mt, pagina)
    for l in lineas:
        h = alto_linea(l)
        if y + h > inicio_pie:
            dibujar_banda(2, ml, inicio_pie, pagina)
            c.showPage(); pagina += 1; y = inicio_lineas
            dibujar_banda(0, ml, mt, pagina)
        dibujar_banda(1, ml, y, pagina, l)
        y += h
    dibujar_banda(2, ml, inicio_pie, pagina)
    c.showPage(); c.save()
    return buf.getvalue() if salida is None else None


def ccc_partes(ccc):
    """Devuelve (entidad, oficina, DC, cuenta) a partir de un CCC o IBAN español."""
    dig = "".join(ch for ch in (ccc or "").upper() if ch.isalnum())
    if dig.startswith("ES"):
        dig = dig[4:]
    if len(dig) != 20:
        return (dig, "", "", "")
    return dig[0:4], dig[4:8], dig[8:10], dig[10:20]

def datos_recibo(empresa, doc, plazo, n_recibo):
    from .letras import importe_a_letras
    imp = dec(plazo.get("importe"))
    e1, e2, dc, cta = ccc_partes(doc.get("ccc"))
    num = (doc.get("serie") or "").strip() + (doc.get("numero") or "")
    return {"NRE": f"{num}/{n_recibo}", "IMP": fmt_eur(imp), "VTO": _fecha(plazo.get("fecha")), "EMI": _fecha(doc.get("fecha")),
            "CON": plazo.get("concepto") or f"Factura nº {num}", "IML": importe_a_letras(imp),
            "CLI": doc.get("nombre_f") or "", "EMP": empresa.get("nombre") or "",
            "Y>DOMICILIA": doc.get("domiciliacion") or "", "X>1": e1, "X>2": e2, "X>3": dc, "X>4": cta,
            "Z>DIRECCIONF": doc.get("direccion_f") or "", "Z>CIUDADF": doc.get("ciudad_f") or "",
            "Z>NOMBREF": doc.get("nombre_f") or "", "Z>CIF": doc.get("nif") or ""}

def render_recibos(fmt_texto, empresa, doc, recibos):
    """recibos: lista de (plazo, nº de recibo). Con diseño Recibo.fmt de FactuCont (modo etiquetas: se usan las
    posiciones de la hoja, un recibo por hueco) o, si no hay diseño, con un modelo sencillo propio."""
    buf = io.BytesIO()
    if not fmt_texto:
        return _recibos_simple(empresa, doc, recibos)
    fdoc, bandas, objs = parse_fmt(fmt_texto)
    W, H = fdoc["PapelAncho"], fdoc["PapelAlto"]
    cp = configparser.RawConfigParser(strict=False); cp.optionxform = str; cp.read_string(fmt_texto)
    filas = cp.getint("Etiquetas", "NumFilas", fallback=1) if cp.has_section("Etiquetas") else 1
    alto = bandas[0] or H
    c = canvas.Canvas(buf, pagesize=(W * mm, H * mm))
    c.setTitle(f"Recibos {(doc.get('serie') or '').strip()}{doc.get('numero')}")
    lz = Lienzo(c, H)
    for i, (plazo, n) in enumerate(recibos):
        hueco = i % max(filas, 1)
        if i and hueco == 0:
            c.showPage()
        x0, y0 = fdoc["Izquierdo"], fdoc["Superior"] + hueco * alto
        val = datos_recibo(empresa, doc, plazo, n)
        for o in objs:
            if int(o.get("Banda", 0)) != 0:
                continue
            t = o.get("Tipo")
            if t == "4": lz.figura(o, x0, y0)
            elif t == "0":
                tx = o.get("Texto", ""); lz.texto(o, x0, y0, [tx[:-1] if tx.endswith(".") else tx])
            elif t in ("2", "5"):
                v = val.get(o.get("Campo", ""), "")
                lz.texto(o, x0, y0, [v], ajustar=True)  # una línea; la letra se reduce si no cabe (importe en letra)
    c.showPage(); c.save()
    return buf.getvalue()

def _recibos_simple(empresa, doc, recibos):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(210 * mm, 297 * mm))
    for i, (plazo, n) in enumerate(recibos):
        if i and i % 3 == 0:
            c.showPage()
        top = 297 - (i % 3) * 99
        v = datos_recibo(empresa, doc, plazo, n)
        c.setStrokeColorRGB(0, 0, 0); c.rect(10 * mm, (top - 92) * mm, 190 * mm, 85 * mm)
        c.setFont("Helvetica-Bold", 14); c.drawString(15 * mm, (top - 17) * mm, "RECIBO")
        c.setFont("Helvetica", 10)
        filas = [("Nº de recibo", v["NRE"]), ("Importe", v["IMP"] + " €"), ("Fecha de expedición", v["EMI"]),
                 ("Vencimiento", v["VTO"]), ("Concepto", v["CON"]), ("Importe en letra", v["IML"]),
                 ("Librado (cliente)", f'{v["CLI"]} — {v["Z>DIRECCIONF"]} {v["Z>CIUDADF"]}'), ("Librador", v["EMP"]),
                 ("Domiciliación", f'{v["Y>DOMICILIA"]} {v["X>1"]} {v["X>2"]} {v["X>3"]} {v["X>4"]}'.strip())]
        y = top - 27
        for k, val in filas:
            c.setFont("Helvetica-Bold", 9); c.drawString(15 * mm, y * mm, k)
            c.setFont("Helvetica", 10); c.drawString(60 * mm, y * mm, str(val)[:95]); y -= 7
    c.showPage(); c.save()
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------ diseño por defecto
def render_pdf_defecto(empresa, doc, lineas, plazos, logo=None, lineas_previas=None):
    """Diseño propio de ContFactu para empresas creadas desde cero (sin diseños .fmt de FactuCont).
    Incluye todo lo que exige el Reglamento de facturación (art. 6 RD 1619/2012): número y serie, fecha,
    datos fiscales de emisor y destinatario, desglose de bases, tipos y cuotas, y total."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from xml.sax.saxutils import escape as esc
    from .calc import totales_cabecera, importe_linea
    AZUL = colors.HexColor("#00407f"); CLARO = colors.HexColor("#dff0ff"); GRIS = colors.HexColor("#667085")
    st = ParagraphStyle("n", fontName="Helvetica", fontSize=9, leading=11.5)
    stb = ParagraphStyle("b", parent=st, fontName="Helvetica-Bold")
    stt = ParagraphStyle("t", parent=st, fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=AZUL, alignment=2)
    stg = ParagraphStyle("g", parent=st, textColor=GRIS, fontSize=8, leading=10)
    titulo = titulo_documento(doc)
    num = (doc.get("serie") or "").strip() + (doc.get("numero") or "")
    P = lambda t, s=st: Paragraph(esc(str(t or "")).replace("\n", "<br/>"), s)

    def lineas_dir(*xs):
        return "\n".join(x for x in xs if x)

    e = empresa
    emisor = [P(e.get("nombre"), ParagraphStyle("e", parent=stb, fontSize=12, leading=15)),
              P(lineas_dir(e.get("direccion"), " ".join(x for x in (e.get("cp"), e.get("ciudad")) if x),
                           e.get("provincia"), f"NIF: {e.get('nif')}" if e.get("nif") else "",
                           " · ".join(x for x in (e.get("telefono"), e.get("email")) if x)))]
    izq = emisor
    if logo:
        try:
            img = Image(logo); r = min(45 * mm / img.drawWidth, 22 * mm / img.drawHeight, 1)
            img.drawWidth *= r; img.drawHeight *= r; img.hAlign = "LEFT"
            izq = [img, Spacer(1, 2 * mm)] + emisor
        except Exception:
            pass
    der = [P(titulo, stt), Spacer(1, 2 * mm),
           Table([["Número", num], ["Fecha", _fecha(doc.get("fecha"))]] +
                 ([["Fecha de operación", _fecha(doc.get("fecha_operacion"))]]
                  if doc.get("fecha_operacion") and doc.get("fecha_operacion") != doc.get("fecha") else []) +
                 ([["Su factura nº", doc.get("num_factura_proveedor")]] if doc.get("num_factura_proveedor") else []),
                 colWidths=[32 * mm, 38 * mm], hAlign="RIGHT",
                 style=[("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9), ("FONT", (1, 0), (1, -1), "Helvetica", 9),
                        ("BACKGROUND", (0, 0), (0, -1), CLARO), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#c5ccd6"))])]
    cab = Table([[izq, der]], colWidths=[100 * mm, 80 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")])
    etiqueta = "Proveedor" if doc.get("tipo") == "G" else "Cliente"
    cliente = Table([[P(etiqueta.upper(), ParagraphStyle("c", parent=stb, textColor=AZUL, fontSize=8))],
                     [P(doc.get("nombre_f"), stb)],
                     [P(lineas_dir(doc.get("direccion_f"), doc.get("ciudad_f"), f"NIF: {doc.get('nif')}" if doc.get("nif") else ""))]],
                    colWidths=[95 * mm], hAlign="RIGHT",
                    style=[("BOX", (0, 0), (-1, -1), .6, AZUL), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 2)])
    filas = [["Código", "Concepto", "Cant.", "Precio", "Dto.", "IVA", "Importe"]]
    estilo = [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
              ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
              ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LINEBELOW", (0, 1), (-1, -1), .3, colors.HexColor("#e4e7ec"))]
    todas = [{"concepto": t, "comentario": 1} for t in (lineas_previas or [])] + list(lineas)
    for l in todas:
        if l.get("comentario") or l.get("precio") in (None, ""):
            filas.append(["", P(l.get("concepto"), ParagraphStyle("i", parent=st, textColor=GRIS)), "", "", "", "", ""])
            continue
        dto = dec(l.get("descuento"))
        filas.append([P(l.get("codigo"), st), P(l.get("concepto")), fmt_eur(dec(l.get("cantidad"))).rstrip("0").rstrip(","),
                      fmt_eur(l.get("precio")), (fmt_eur(dto).rstrip("0").rstrip(",") + "%") if dto else "",
                      fmt_eur(dec(l.get("iva"))).rstrip("0").rstrip(",") + "%", fmt_eur(importe_linea(l))])
    tabla = Table(filas, colWidths=[20 * mm, 78 * mm, 15 * mm, 20 * mm, 13 * mm, 12 * mm, 22 * mm], repeatRows=1, style=estilo)
    t = totales_cabecera(doc)
    hay_re = any(x["cuota_re"] for x in t["desglose"])
    cab_iva = ["Base imponible", "% IVA", "Cuota IVA"] + (["% RE", "Cuota RE"] if hay_re else [])
    des = [cab_iva] + [[fmt_eur(x["base"]), fmt_eur(x["iva"]).rstrip("0").rstrip(",") + "%", fmt_eur(x["cuota_iva"])] +
                       ([fmt_eur(x["re"]).rstrip("0").rstrip(",") + "%", fmt_eur(x["cuota_re"])] if hay_re else [])
                       for x in t["desglose"]]
    if doc.get("exento"):
        des.append(["Operación exenta de IVA"] + [""] * (len(cab_iva) - 1))
    tot = [["Base imponible", fmt_eur(t["base"], True)], ["IVA", fmt_eur(t["cuota_iva"], True)]]
    if t["cuota_re"]:
        tot.append(["Recargo de equivalencia", fmt_eur(t["cuota_re"], True)])
    if t["retencion"]:
        tot.append([f"Retención IRPF {fmt_eur(dec(doc.get('retencion'))).rstrip('0').rstrip(',')}%", "-" + fmt_eur(t["retencion"], True)])
    tot.append(["TOTAL", fmt_eur(t["total"], True)])
    pie = Table([[Table(des, style=[("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
                                    ("BACKGROUND", (0, 0), (-1, 0), CLARO), ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                                    ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#c5ccd6"))]),
                  Table(tot, colWidths=[42 * mm, 30 * mm],
                        style=[("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                               ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11), ("BACKGROUND", (0, -1), (-1, -1), CLARO),
                               ("LINEABOVE", (0, -1), (-1, -1), 1, AZUL)])]],
                colWidths=[105 * mm, 75 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")])
    historia = [cab, Spacer(1, 5 * mm), cliente, Spacer(1, 6 * mm), tabla, Spacer(1, 5 * mm), pie]
    venc = [p for p in plazos if p.get("tipo") != "1" and dec(p.get("importe"))]
    extra = []
    if doc.get("forma_pago"):
        extra.append(f"<b>Forma de pago:</b> {esc(doc['forma_pago'])}")
    if venc:
        extra.append("<b>Vencimientos:</b> " + "; ".join(f"{_fecha(p.get('fecha'))}: {fmt_eur(p.get('importe'), True)}" for p in venc))
    if doc.get("ccc") and doc.get("tipo") != "G":
        extra.append(f"<b>Domiciliación:</b> {esc(doc.get('ccc'))}")
    elif e.get("ccc") and doc.get("tipo") == "F":
        extra.append(f"<b>Pago por transferencia a:</b> {esc(e.get('ccc'))}{(' · BIC ' + esc(e['bic'])) if e.get('bic') else ''}")
    if doc.get("rect_motivo"):
        extra.append(f"<b>Motivo de la rectificación:</b> {esc(doc['rect_motivo'])}")
    for x in extra:
        historia += [Spacer(1, 2 * mm), Paragraph(x, st)]

    def pie_pagina(c, d):
        c.saveState(); c.setFont("Helvetica", 7.5); c.setFillColor(GRIS)
        c.drawString(15 * mm, 9 * mm, f"{e.get('nombre') or ''} · NIF {e.get('nif') or ''}")
        c.drawRightString(195 * mm, 9 * mm, f"{titulo.capitalize()} {num} · página {d.page}")
        c.restoreState()

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=(210 * mm, 297 * mm), leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=f"{titulo} {num}", author=e.get("nombre") or "", creator=f"ContFactu")
    pdf.build(historia, onFirstPage=pie_pagina, onLaterPages=pie_pagina)
    return buf.getvalue()
