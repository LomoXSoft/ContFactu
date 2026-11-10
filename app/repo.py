"""Lógica de negocio: consulta, alta, edición y borrado de documentos, rectificativas, cobros, conversión a factura
y libros de IVA. Todas las funciones reciben una conexión y NO hacen commit (lo hace quien llama con `with con:`)."""
import datetime, re
from decimal import Decimal as D
from .calc import bases_desde_lineas, totales_cabecera, dec, r2, fmt_eur, tramos_iva, desglose_json, tipo_iva_valido, descuento_valido

TASAS_RE = {dec(21): dec("5.2"), dec(10): dec("1.4"), dec(5): dec("0.62"), dec(4): dec("0.5")}
RE_DEFECTO = "21:5.2,10:1.4,5:0.62,4:0.5"   # recargo de equivalencia por tipo de IVA (editable en la ficha de la empresa)

def parse_tasas_re(txt):
    """«21:5.2,10:1.4» -> {Decimal(21): Decimal('5.2'), ...}. Lanza ValueError si algún tipo no es válido."""
    res = {}
    for par in (txt if txt is not None else RE_DEFECTO).replace(";", ",").split(","):
        if not par.strip():
            continue
        if ":" not in par:
            raise ValueError(f"Recargo no válido: «{par.strip()}» (formato IVA:RE, p. ej. 21:5,2).")
        iva, re_ = par.split(":", 1)
        res[dec(tipo_iva_valido(iva))] = dec(tipo_iva_valido(re_, etiqueta="El recargo de equivalencia"))
    return res

def tasas_re_empresa(con, eid):
    r = con.execute("SELECT re_tasas FROM empresas WHERE id=?", (eid,)).fetchone()
    try:
        return parse_tasas_re(r[0] if r and r[0] is not None else None)
    except ValueError:
        return dict(TASAS_RE)
SERIE_RECTIFICATIVA = "R"
MOTIVOS_R = {  # tipos de factura rectificativa del Reglamento de facturación / VeriFactu
    "R1": "Error fundado en derecho y art. 80 Uno, Dos y Seis LIVA",
    "R2": "Concurso de acreedores (art. 80 Tres LIVA)",
    "R3": "Créditos incobrables (art. 80 Cuatro LIVA)",
    "R4": "Resto de causas (errores, devoluciones, descuentos...)",
}

class ErrorNegocio(Exception):
    """Error explicable al usuario. `campo` es el name del input; `indice` la fila, desde 0, si hay varias."""
    def __init__(self, mensaje, campo=None, indice=None):
        super().__init__(mensaje)
        self.campo = campo
        self.indice = indice

class AvisoNumeracion(ErrorNegocio):
    """Borrar esta factura deja un hueco en la numeración: hay que confirmarlo expresamente."""

def hoy():
    return datetime.date.today().isoformat()

def _f(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""

def _pc(v):
    return format(dec(v).normalize(), "f").replace(".", ",")

def num_visible(d):
    return (d.get("serie") or "").strip() + (d.get("numero") or "")

# ----------------------------------------------------------------------------------------------- consultas
def empresas(con):
    return [dict(r) for r in con.execute("""SELECT e.*, (SELECT COUNT(*) FROM documentos d WHERE d.empresa_id=e.id AND d.tipo='F') AS n_facturas,
        (SELECT MAX(fecha) FROM documentos d WHERE d.empresa_id=e.id) AS ultima FROM empresas e ORDER BY codigo""")]

def empresa(con, eid):
    r = con.execute("SELECT * FROM empresas WHERE id=?", (eid,)).fetchone()
    return dict(r) if r else None

def documento(con, did):
    r = con.execute("SELECT * FROM documentos WHERE id=?", (did,)).fetchone()
    if not r:
        return None, [], []
    ls = [dict(x) for x in con.execute("SELECT * FROM lineas WHERE documento_id=? ORDER BY orden", (did,))]
    ps = [dict(x) for x in con.execute("SELECT * FROM plazos WHERE documento_id=? ORDER BY fecha, id", (did,))]
    return dict(r), ls, ps

def doc(con, did):
    r = con.execute("SELECT * FROM documentos WHERE id=?", (did,)).fetchone()
    if not r:
        raise ErrorNegocio("El documento no existe.")
    return dict(r)

def formato(con, eid, clase):
    """Diseño .fmt de la empresa para 'factura', 'presupuesto', 'albaran' o 'recibo' (None si no hay)."""
    r = con.execute("SELECT texto FROM formatos WHERE empresa_id=? AND clase=?", (eid, clase)).fetchone()
    if r and r[0]:
        return r[0]
    if clase == "recibo":
        return None
    e = empresa(con, eid)
    return (e or {}).get("formato_factura")

CLASE_FORMATO = {"F": "factura", "P": "presupuesto", "A": "albaran", "M": "factura", "D": "presupuesto", "G": "factura"}

# ----------------------------------------------------------------------------------------------- numeración
def _correlativo(numero, aa):
    m = re.fullmatch(aa + r"(\d+)", numero or "")
    return int(m.group(1)) if m else None

def siguiente_numero(con, eid, tipo="F", serie="", fecha=None):
    """Numeración FactuCont: [serie 3 car.][AA][correlativo]. Se respeta el ancho usado ese año (4 o 5 cifras)
    y el contador vuelve a 1 cada año, por serie."""
    fecha = fecha or hoy()
    aa = fecha[2:4]
    mx, ancho = 0, None
    for (num,) in con.execute("SELECT numero FROM documentos WHERE empresa_id=? AND tipo=? AND serie=? AND numero LIKE ?",
                              (eid, tipo, serie, aa + "%")):
        n = _correlativo(num, aa)
        if n is not None and n >= mx:
            mx, ancho = n, len(num) - 2
    if ancho is None:  # primer documento del año: copiar ancho del año anterior más reciente
        r = con.execute("SELECT numero FROM documentos WHERE empresa_id=? AND tipo=? AND serie=? ORDER BY fecha DESC, id DESC LIMIT 1",
                        (eid, tipo, serie)).fetchone()
        ancho = max(len(r[0]) - 2, 4) if r and r[0] and r[0].isdigit() else 4
        if r is None and tipo == "F":
            # Primera factura de la serie en ContFactu: empresa nueva que continúa la numeración de otro programa
            e = con.execute("SELECT serie_defecto, contador_inicial FROM empresas WHERE id=?", (eid,)).fetchone()
            if e and (e[0] or "") == serie and (e[1] or 0) > 1:
                mx = int(e[1]) - 1
                ancho = max(ancho, len(str(e[1])))
    return f"{aa}{mx + 1:0{ancho}d}"

def vecinas_en_serie(con, d):
    """(anterior, siguiente) de la misma serie y año, por número."""
    aa = (d.get("numero") or "")[:2]
    n = _correlativo(d.get("numero"), aa)
    if n is None:
        return None, None
    ant = sig = None
    for r in con.execute("SELECT * FROM documentos WHERE empresa_id=? AND tipo=? AND serie=? AND numero LIKE ? AND id<>?",
                         (d["empresa_id"], d["tipo"], d["serie"], aa + "%", d.get("id") or -1)):
        m = _correlativo(r["numero"], aa)
        if m is None:
            continue
        if m < n and (ant is None or m > ant[0]): ant = (m, dict(r))
        if m > n and (sig is None or m < sig[0]): sig = (m, dict(r))
    return (ant[1] if ant else None), (sig[1] if sig else None)

def es_ultima_de_serie(con, d):
    return vecinas_en_serie(con, d)[1] is None

def _comprobar_fecha_serie(con, d, fecha):
    """Las facturas de una serie deben tener fechas en el mismo orden que sus números (art. 6 RD 1619/2012)."""
    if d["tipo"] != "F":
        return
    ant, sig = vecinas_en_serie(con, dict(d, fecha=fecha))
    if ant and ant.get("fecha") and fecha < ant["fecha"]:
        raise ErrorNegocio(f"La fecha {_f(fecha)} es anterior a la de la factura {num_visible(ant)} ({_f(ant['fecha'])}). "
                           "En una misma serie las fechas deben seguir el orden de la numeración.", campo="fecha")
    if sig and sig.get("fecha") and fecha > sig["fecha"]:
        raise ErrorNegocio(f"La fecha {_f(fecha)} es posterior a la de la factura {num_visible(sig)} ({_f(sig['fecha'])}). "
                           "En una misma serie las fechas deben seguir el orden de la numeración.", campo="fecha")

# ----------------------------------------------------------------------------------------------- cálculo
def limpiar_lineas(lineas):
    res = []
    for l in lineas:
        concepto = (l.get("concepto") or "").strip()
        precio = l.get("precio")
        coment = bool(l.get("comentario")) or precio in (None, "")
        if not concepto and (coment or dec(precio) == 0):
            continue
        res.append({"codigo": l.get("codigo") or "", "concepto": concepto, "cantidad": "" if coment else str(l.get("cantidad") or "1"),
                    "precio": "" if coment else str(precio), "descuento": "" if coment else str(l.get("descuento") or "0"),
                    "iva": "" if coment else str(l.get("iva") if l.get("iva") not in (None, "") else "21"),
                    "comentario": int(coment), "fecha": l.get("fecha")})
    return res

def calcular_cabecera(lineas, descuento="0", retencion="0", con_re=False, exento=False, iva_incluido=False, tasas_re=None):
    """Bases por tipo de IVA (sin límite de tipos), RE, retención y total.
    El desglose completo se guarda en «desglose_iva»; base1..3/iva1..3/re1..3 conservan los tres primeros tipos para
    compatibilidad con los diseños de FactuCont y con versiones anteriores. tasas_re: {iva: re} de la empresa."""
    tasas = TASAS_RE if tasas_re is None else tasas_re
    bases = bases_desde_lineas(lineas, descuento, iva_incluido)
    tramos = [(b, iva, (tasas.get(iva, D(0)) if con_re else D(0))) for iva, b in sorted(bases.items(), key=lambda x: -x[0])]
    cols = {f"{k}{i}": None for i in (1, 2, 3) for k in ("base", "iva", "re")}
    for i, (b, iva, re) in enumerate(tramos[:3], 1):
        cols[f"base{i}"], cols[f"iva{i}"], cols[f"re{i}"] = str(b), format(iva, "f"), format(re, "f")
    cols["desglose_iva"] = desglose_json(tramos)
    cab = dict(cols, retencion=str(retencion or "0"), exento=int(bool(exento)))
    tot = totales_cabecera(cab)
    cab["retenido"], cab["total"] = str(tot["retencion"]), str(tot["total"])
    return cab, tot

def _con_re(d):
    return any(r != 0 for _, _, r in tramos_iva(d))

def validar_lineas_iva(lineas):
    """Cada línea puede llevar cualquier tipo de IVA entre 0 y 100, ambos incluidos, con los decimales que se escriban.
    El descuento de la línea es un porcentaje en el mismo rango. indice es la posición en la lista, desde 0."""
    for n, l in enumerate(lineas):
        if l.get("comentario"):
            continue
        try:
            l["iva"] = tipo_iva_valido(l.get("iva"))
        except ValueError as ex:
            raise ErrorNegocio(str(ex), campo="iva", indice=n)
        try:
            l["descuento"] = descuento_valido(l.get("descuento"))
        except ValueError as ex:
            raise ErrorNegocio(str(ex), campo="descuento", indice=n)
    return lineas

CAMPOS_CAB = ("fecha", "fecha_operacion", "nombre_f", "direccion_f", "ciudad_f", "nif", "cliente_codigo", "forma_pago",
              "dias_pago", "domiciliacion", "ccc", "bic", "num_factura_proveedor", "deducible")

def _insertar_lineas(con, did, lineas, fecha):
    con.execute("DELETE FROM lineas WHERE documento_id=?", (did,))
    for i, l in enumerate(lineas, 1):
        con.execute("INSERT INTO lineas(documento_id,orden,codigo,concepto,cantidad,precio,descuento,iva,comentario,fecha) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (did, i, l.get("codigo"), l.get("concepto"), l.get("cantidad"), l.get("precio"), l.get("descuento"),
                     l.get("iva"), l.get("comentario"), l.get("fecha") or fecha))

def _regenerar_vencimientos(con, d, nuevo_pendiente):
    """Rehace los vencimientos no cobrados para que sumen el nuevo pendiente; los cobrados se conservan."""
    did = d["id"]
    con.execute("DELETE FROM plazos WHERE documento_id=? AND tipo='1'", (did,))
    con.execute("DELETE FROM plazos WHERE documento_id=? AND tipo='' AND CAST(cobrado AS REAL)=0", (did,))
    resto = [dict(r) for r in con.execute("SELECT * FROM plazos WHERE documento_id=? AND tipo=''", (did,))]
    abierto = sum(dec(p["importe"]) - dec(p["cobrado"]) for p in resto)
    ref = d["tipo"] + d["numero_raw"]
    con.execute("INSERT INTO plazos(documento_id,empresa_id,referencia,tipo,fecha,concepto,importe,cobrado) VALUES(?,?,?,?,?,?,?,'0')",
                (did, d["empresa_id"], ref, "1", d["fecha"], f"Importe fra. {num_visible(d)}", str(-dec(d["total"]))))
    falta = r2(dec(nuevo_pendiente) - abierto)
    if falta != 0:
        n = con.execute("SELECT COUNT(*) FROM plazos WHERE documento_id=? AND tipo IN ('','A')", (did,)).fetchone()[0] + 1
        con.execute("INSERT INTO plazos(documento_id,empresa_id,referencia,tipo,fecha,concepto,importe,cobrado) VALUES(?,?,?,?,?,?,?,'0')",
                    (did, d["empresa_id"], ref, "", d["fecha"], f"Plazo nº {n} fra. {num_visible(d)}", str(falta)))

# ----------------------------------------------------------------------------------------------- alta y edición
def guardar_documento(con, eid, tipo, datos, lineas, did=None):
    """Crea (did=None) o modifica un documento de cualquier tipo. Recalcula siempre bases, cuotas y total.
    datos: fecha, serie, nombre_f..., descuento, retencion, re (bool), exento, iva_incluido. Devuelve el id."""
    lineas = validar_lineas_iva(limpiar_lineas(lineas))
    if not lineas:
        raise ErrorNegocio("El documento no tiene líneas.")
    fecha = datos.get("fecha") or hoy()
    try:
        datetime.date.fromisoformat(fecha)
    except ValueError:
        raise ErrorNegocio(f"Fecha no válida: {fecha}", campo="fecha")
    try:
        descuento = descuento_valido(datos.get("descuento"))
    except ValueError as ex:
        raise ErrorNegocio(str(ex), campo="descuento")
    cab, tot = calcular_cabecera(lineas, descuento, datos.get("retencion") or "0", datos.get("re"),
                                 datos.get("exento"), datos.get("iva_incluido"), tasas_re=tasas_re_empresa(con, eid))
    valores = {k: datos.get(k) for k in CAMPOS_CAB if k in datos}
    valores["fecha"] = fecha
    valores.setdefault("fecha_operacion", fecha)
    valores.update(cab, descuento=descuento, iva_incluido=int(bool(datos.get("iva_incluido"))))
    if did is None:
        serie = (datos.get("serie") or "").strip()[:3]
        numero = datos.get("numero") or siguiente_numero(con, eid, tipo, serie, fecha)
        if tipo == "F":
            _comprobar_fecha_serie(con, {"empresa_id": eid, "tipo": tipo, "serie": serie, "numero": numero}, fecha)
        raw = serie.rjust(3) + numero if serie else "   " + numero
        if con.execute("SELECT 1 FROM documentos WHERE empresa_id=? AND tipo=? AND numero_raw=?", (eid, tipo, raw)).fetchone():
            raise ErrorNegocio(f"Ya existe el documento número {serie}{numero}.")
        valores.update(empresa_id=eid, tipo=tipo, numero_raw=raw, serie=serie, numero=numero, origen="nuevo",
                       pendiente=cab["total"], vf_tipo_factura=datos.get("vf_tipo_factura") or ("F1" if tipo == "F" else None),
                       vf_estado="no_aplica", facturado=0)
        cols = list(valores)
        did = con.execute(f"INSERT INTO documentos({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [valores[c] for c in cols]).lastrowid
        d = doc(con, did)
        _insertar_lineas(con, did, lineas, fecha)
        _regenerar_vencimientos(con, d, d["pendiente"])
        return did
    d = doc(con, did)
    if d["empresa_id"] != eid or d["tipo"] != tipo:
        raise ErrorNegocio("El documento no pertenece a esta empresa o tipo.")
    _comprobar_fecha_serie(con, d, fecha)
    cobrado = dec(d["total"]) - dec(d["pendiente"])
    nuevo_total = dec(cab["total"])
    if cobrado != 0 and (abs(cobrado) > abs(nuevo_total) or (cobrado > 0) != (nuevo_total > 0)):
        raise ErrorNegocio(f"Ya hay {fmt_eur(cobrado)} € cobrados y el nuevo total sería {fmt_eur(nuevo_total)} €. "
                           "Anule antes los cobros sobrantes.")
    valores["pendiente"] = str(r2(nuevo_total - cobrado))
    if d["origen"] == "factucont":
        valores["origen"] = "editado"  # así una reimportación no pisa los cambios
    sets = ",".join(f"{k}=?" for k in valores)
    con.execute(f"UPDATE documentos SET {sets} WHERE id=?", list(valores.values()) + [did])
    con.execute("DELETE FROM verificacion WHERE documento_id=?", (did,))
    _insertar_lineas(con, did, lineas, fecha)
    _regenerar_vencimientos(con, doc(con, did), valores["pendiente"])
    return did

def crear_factura(con, eid, datos, lineas, tipo="F"):
    """Compatibilidad con la primera versión. Devuelve (id, número)."""
    did = guardar_documento(con, eid, tipo, datos, lineas)
    return did, doc(con, did)["numero"]

def datos_de(d):
    """Cabecera de un documento en el formato que espera guardar_documento."""
    x = {k: d.get(k) for k in CAMPOS_CAB}
    x.update(serie=(d.get("serie") or "").strip(), descuento=d.get("descuento") or "0", retencion=d.get("retencion") or "0",
             re=_con_re(d), exento=bool(d.get("exento")), iva_incluido=bool(d.get("iva_incluido")))
    return x

# ----------------------------------------------------------------------------------------------- borrado
def info_borrado(con, did):
    """Qué pasa si se borra: avisos y bloqueos, para la pantalla de confirmación."""
    d = doc(con, did)
    avisos, bloqueos = [], []
    if d["tipo"] == "F":
        if not es_ultima_de_serie(con, d):
            _, sig = vecinas_en_serie(con, d)
            avisos.append(f"No es la última factura de su serie (después va la {num_visible(sig)}). Si la borra quedará un "
                          "HUECO en la numeración correlativa, que Hacienda exige sin saltos. Lo correcto es emitir una "
                          "FACTURA RECTIFICATIVA que la anule.")
        rects = con.execute("SELECT serie, numero FROM documentos WHERE rect_original_id=?", (did,)).fetchall()
        if rects:
            bloqueos.append("Tiene rectificativas (" + ", ".join(r[0] + r[1] for r in rects) + "): bórrelas antes.")
        origenes = con.execute("SELECT tipo, serie, numero FROM documentos WHERE facturado_en_id=?", (did,)).fetchall()
        if origenes:
            avisos.append("Los documentos de origen (" + ", ".join(r[1].strip() + r[2] for r in origenes) +
                          ") volverán a quedar como «no facturados».")
    cobrado = dec(d["total"]) - dec(d["pendiente"])
    if d["tipo"] in ("F", "A", "M") and cobrado != 0:
        avisos.append(f"Tiene {fmt_eur(cobrado)} € cobrados; los cobros se borrarán con el documento.")
    if d.get("facturado_en_id"):
        avisos.append("Este documento ya está facturado; la factura generada no se modifica.")
    return {"doc": d, "avisos": avisos, "bloqueos": bloqueos, "rompe_numeracion": d["tipo"] == "F" and not es_ultima_de_serie(con, d)}

def borrar_documento(con, did, forzar=False):
    info = info_borrado(con, did)
    d = info["doc"]
    if info["bloqueos"]:
        raise ErrorNegocio(" ".join(info["bloqueos"]))
    if info["rompe_numeracion"] and not forzar:
        raise AvisoNumeracion(info["avisos"][0])
    if d.get("rect_tipo") == "S" and d.get("rect_original_id"):  # devolver el pendiente a la original
        con.execute("UPDATE documentos SET pendiente=? WHERE id=?", (d.get("rect_pendiente_original") or "0", d["rect_original_id"]))
    con.execute("UPDATE documentos SET facturado=0, facturado_en_id=NULL WHERE facturado_en_id=?", (did,))
    con.execute("DELETE FROM verificacion WHERE documento_id=?", (did,))
    con.execute("DELETE FROM documentos WHERE id=?", (did,))  # líneas, plazos y cobros en cascada
    return d

# ----------------------------------------------------------------------------------------------- rectificativas
def lineas_por_defecto_rectificativa(con, did_orig, rect_tipo):
    _, ls, _ = documento(con, did_orig)
    res = []
    for l in ls:
        l = dict(l)
        if rect_tipo == "I" and not l.get("comentario"):
            l["cantidad"] = format(-dec(l.get("cantidad") or 1), "f")
        res.append(l)
    return res

def crear_rectificativa(con, did_orig, rect_tipo, motivo, codigo_r="R4", fecha=None, lineas=None, serie=SERIE_RECTIFICATIVA,
                        cabecera=None):
    """rect_tipo 'I' por diferencias (importes = diferencia, normalmente negativos) o 'S' por sustitución (importes = factura
    correcta completa; la original queda anulada a efectos de cobro). Serie propia (R por defecto)."""
    o = doc(con, did_orig)
    if o["tipo"] != "F":
        raise ErrorNegocio("Solo se pueden rectificar facturas emitidas.")
    if rect_tipo not in ("I", "S"):
        raise ErrorNegocio("Indique si es por diferencias o por sustitución.", campo="rect_tipo")
    if codigo_r not in MOTIVOS_R:
        raise ErrorNegocio("Tipo de rectificativa no válido (R1 a R4).", campo="codigo_r")
    if not (motivo or "").strip():
        raise ErrorNegocio("Indique el motivo de la rectificación (obligatorio en la factura).", campo="rect_motivo")
    fecha = fecha or hoy()
    if fecha < (o["fecha"] or ""):
        raise ErrorNegocio("La rectificativa no puede tener fecha anterior a la factura que rectifica.")
    if lineas is None:
        lineas = lineas_por_defecto_rectificativa(con, did_orig, rect_tipo)
    datos = datos_de(o)
    datos.update({k: v for k, v in (cabecera or {}).items() if k not in ("serie", "fecha", "numero") and v is not None})
    datos.update(fecha=fecha, fecha_operacion=o.get("fecha_operacion") or o["fecha"], serie=serie, vf_tipo_factura=codigo_r)
    did = guardar_documento(con, o["empresa_id"], "F", datos, lineas)
    tot_o = totales_cabecera(o)
    upd = {"rect_original_id": did_orig, "rect_tipo": rect_tipo, "rect_motivo": motivo.strip(),
           "rect_base_original": str(tot_o["base"]), "rect_cuota_original": str(tot_o["cuota_iva"] + tot_o["cuota_re"])}
    if rect_tipo == "S":
        # lo cobrado de la original se traslada a la nueva; la original deja de estar pendiente
        cobrado_o = dec(o["total"]) - dec(o["pendiente"])
        nueva = doc(con, did)
        upd["rect_pendiente_original"] = o["pendiente"] or "0"
        upd["pendiente"] = str(r2(dec(nueva["total"]) - cobrado_o))
        con.execute("UPDATE documentos SET pendiente='0' WHERE id=?", (did_orig,))
    con.execute(f"UPDATE documentos SET {','.join(k + '=?' for k in upd)} WHERE id=?", list(upd.values()) + [did])
    if rect_tipo == "S":
        _regenerar_vencimientos(con, doc(con, did), upd["pendiente"])
    else:
        # por diferencias: el abono reduce lo que el cliente debe de la original, si aún debe algo
        nueva = doc(con, did)
        if dec(nueva["total"]) < 0 and dec(o["pendiente"]) > 0:
            compensa = min(-dec(nueva["total"]), dec(o["pendiente"]))
            registrar_cobro(con, did_orig, compensa, fecha, "Compensación", f"Rectificativa {num_visible(nueva)}")
            registrar_cobro(con, did, -compensa, fecha, "Compensación", f"Aplicada a la factura {num_visible(o)}")
    return did

def lineas_referencia_rectificativa(con, d):
    """Texto que se imprime en el PDF de una rectificativa (referencia a la original, motivo y tipo)."""
    if not d.get("rect_original_id"):
        return []
    o = con.execute("SELECT * FROM documentos WHERE id=?", (d["rect_original_id"],)).fetchone()
    ref = f"{num_visible(dict(o))} de fecha {_f(o['fecha'])}" if o else "(factura original no disponible)"
    tipo = "por sustitución" if d.get("rect_tipo") == "S" else "por diferencias"
    res = [f"Rectifica a la factura nº {ref} ({tipo}).", f"Motivo: {d.get('rect_motivo') or ''}"]
    if d.get("rect_tipo") == "S":
        res.append(f"Importes originales: base {fmt_eur(d.get('rect_base_original'))} €, cuota {fmt_eur(d.get('rect_cuota_original'))} €.")
    return res + [""]

# ----------------------------------------------------------------------------------------------- cobros
def registrar_cobro(con, did, importe, fecha=None, forma="", nota="", plazo_id=None):
    """Cobro total o parcial. Se aplica a los vencimientos abiertos por orden de fecha (o al indicado)."""
    d = doc(con, did)
    imp = r2(dec(importe))
    pend = dec(d["pendiente"])
    if imp == 0:
        raise ErrorNegocio("El importe del cobro no puede ser cero.")
    if pend == 0:
        raise ErrorNegocio("Este documento no tiene nada pendiente de cobro.")
    if (imp > 0) != (pend > 0) or abs(imp) > abs(pend):
        raise ErrorNegocio(f"El cobro ({fmt_eur(imp)} €) no puede superar lo pendiente ({fmt_eur(pend)} €).")
    fecha = fecha or hoy()
    sql = "SELECT * FROM plazos WHERE documento_id=? AND tipo='' " + ("AND id=? " if plazo_id else "") + "ORDER BY fecha, id"
    plazos = [dict(p) for p in con.execute(sql, (did, plazo_id) if plazo_id else (did,))]
    resto = imp
    for p in plazos:
        abierto = dec(p["importe"]) - dec(p["cobrado"])
        if resto == 0 or abierto == 0 or (abierto > 0) != (resto > 0):
            continue
        parte = min(abs(resto), abs(abierto)) * (1 if resto > 0 else -1)
        con.execute("UPDATE plazos SET cobrado=? WHERE id=?", (str(r2(dec(p["cobrado"]) + parte)), p["id"]))
        con.execute("INSERT INTO cobros(documento_id,plazo_id,fecha,importe,forma,nota) VALUES(?,?,?,?,?,?)",
                    (did, p["id"], fecha, str(parte), forma, nota))
        resto -= parte
    if resto != 0:  # vencimientos de FactuCont que no cuadran con el pendiente: el resto va sin vencimiento
        con.execute("INSERT INTO cobros(documento_id,plazo_id,fecha,importe,forma,nota) VALUES(?,?,?,?,?,?)",
                    (did, None, fecha, str(resto), forma, nota))
    con.execute("UPDATE documentos SET pendiente=? WHERE id=?", (str(r2(pend - imp)), did))

def anular_cobro(con, cobro_id):
    c = con.execute("SELECT * FROM cobros WHERE id=?", (cobro_id,)).fetchone()
    if not c:
        raise ErrorNegocio("El cobro no existe.")
    imp = dec(c["importe"])
    if c["plazo_id"]:
        con.execute("UPDATE plazos SET cobrado=CAST(? AS TEXT) WHERE id=?",
                    (str(r2(dec(con.execute("SELECT cobrado FROM plazos WHERE id=?", (c["plazo_id"],)).fetchone()[0]) - imp)), c["plazo_id"]))
    d = doc(con, c["documento_id"])
    con.execute("UPDATE documentos SET pendiente=? WHERE id=?", (str(r2(dec(d["pendiente"]) + imp)), d["id"]))
    con.execute("DELETE FROM cobros WHERE id=?", (cobro_id,))
    return d["id"]

def cobros(con, did):
    return [dict(r) for r in con.execute("SELECT * FROM cobros WHERE documento_id=? ORDER BY fecha, id", (did,))]

def estado_cobro(d):
    pend, tot = dec(d.get("pendiente")), dec(d.get("total"))
    if pend == 0: return "cobrado"
    if pend == tot: return "pendiente"
    return "parcial"

def pendientes(con, eid, hasta=None):
    """Facturas y albaranes (sin facturar) con importe pendiente, con sus vencimientos abiertos."""
    hasta = hasta or hoy()
    res = []
    for d in con.execute("""SELECT * FROM documentos WHERE empresa_id=? AND CAST(pendiente AS REAL)<>0 AND
            (tipo='F' OR (tipo='A' AND COALESCE(facturado,0)=0)) ORDER BY fecha, numero""", (eid,)):
        d = dict(d)
        vtos = [dict(p) for p in con.execute("SELECT * FROM plazos WHERE documento_id=? AND tipo='' ORDER BY fecha", (d["id"],))
                if dec(p["importe"]) - dec(p["cobrado"]) != 0]
        d["vencimiento"] = vtos[0]["fecha"] if vtos else d["fecha"]
        d["vencido"] = d["vencimiento"] < hasta
        d["estado"] = estado_cobro(d)
        d["vencimientos"] = vtos
        res.append(d)
    return res

def alertas_cobro(con, eid, dias=7, hoy_=None):
    """Resumen de vencimientos de cobro ya vencidos y de los que vencen en los próximos `dias` días (incluido hoy)."""
    hoy_ = hoy_ or hoy()
    limite = (datetime.date.fromisoformat(hoy_) + datetime.timedelta(days=dias)).isoformat()
    vencidos, proximos = [], []
    for d in pendientes(con, eid, hoy_):
        vtos = d["vencimientos"] or [{"fecha": d["fecha"], "importe": d["pendiente"], "cobrado": "0"}]
        for p in vtos:
            imp = dec(p["importe"]) - dec(p.get("cobrado"))
            if imp <= 0 or not p.get("fecha"):
                continue
            x = {"documento_id": d["id"], "numero": num_visible(d), "tipo": d["tipo"], "cliente": d.get("nombre_f") or "",
                 "fecha": p["fecha"], "importe": imp}
            if p["fecha"] < hoy_:
                vencidos.append(x)
            elif p["fecha"] <= limite:
                proximos.append(x)
    vencidos.sort(key=lambda x: x["fecha"]); proximos.sort(key=lambda x: x["fecha"])
    return {"vencidos": vencidos, "proximos": proximos, "dias": dias,
            "importe_vencido": sum((x["importe"] for x in vencidos), D(0)),
            "importe_proximo": sum((x["importe"] for x in proximos), D(0)), "hay": bool(vencidos or proximos)}

def recibos_documento(con, did):
    """Vencimientos imprimibles como recibo: (plazo, nº de recibo correlativo dentro del documento)."""
    ps = [dict(p) for p in con.execute("SELECT * FROM plazos WHERE documento_id=? AND tipo IN ('','A') AND CAST(importe AS REAL)<>0 ORDER BY fecha, id", (did,))]
    return [(p, i) for i, p in enumerate(ps, 1)]

# ----------------------------------------------------------------------------------------------- facturar
def facturables(con, eid, tipo="A", cliente=None):
    sql = "SELECT * FROM documentos WHERE empresa_id=? AND tipo=? AND COALESCE(facturado,0)=0"
    args = [eid, tipo]
    if cliente:
        sql += " AND nombre_f=?"; args.append(cliente)
    return [dict(r) for r in con.execute(sql + " ORDER BY nombre_f, fecha", args)]

def _clave_cliente(d):
    return ((d.get("nif") or "").replace(" ", "").replace("-", "").upper()) or (d.get("nombre_f") or "").strip().upper()

def facturar(con, ids, fecha=None, serie=""):
    """Convierte uno o varios presupuestos/albaranes (mismo cliente) en una factura. Marca el origen como facturado."""
    if not ids:
        raise ErrorNegocio("Seleccione al menos un documento.")
    ds = [doc(con, i) for i in ids]
    tipos = {d["tipo"] for d in ds}
    if not tipos <= {"A", "P", "D"} or len(tipos) != 1:
        raise ErrorNegocio("Solo se pueden facturar presupuestos, pedidos o albaranes, y todos del mismo tipo.")
    if len({d["empresa_id"] for d in ds}) != 1:
        raise ErrorNegocio("Los documentos son de empresas distintas.")
    if len({_clave_cliente(d) for d in ds}) != 1:
        raise ErrorNegocio("Todos los documentos deben ser del mismo cliente.")
    ya = [num_visible(d) for d in ds if d.get("facturado")]
    if ya:
        raise ErrorNegocio("Ya están facturados: " + ", ".join(ya))
    for k, txt in (("descuento", "descuento general"), ("retencion", "retención")):
        if len({dec(d.get(k)) for d in ds}) != 1:
            raise ErrorNegocio(f"Los documentos tienen distinto {txt}; facture por separado.")
    if len({_con_re(d) for d in ds}) != 1:
        raise ErrorNegocio("Unos documentos llevan recargo de equivalencia y otros no; facture por separado.")
    ds.sort(key=lambda d: (d["fecha"] or "", d["numero"]))
    nombre = {"A": "Albarán", "P": "Presupuesto", "D": "Pedido"}[ds[0]["tipo"]]
    lineas = []
    for d in ds:
        _, ls, _ = documento(con, d["id"])
        lineas.append({"concepto": f"{nombre} nº {num_visible(d)} de fecha {_f(d['fecha'])}", "comentario": 1})
        lineas += ls
    datos = datos_de(ds[-1])
    datos.update(fecha=fecha or hoy(), fecha_operacion=ds[-1]["fecha"], serie=serie)
    did = guardar_documento(con, ds[0]["empresa_id"], "F", datos, lineas)
    for d in ds:
        con.execute("UPDATE documentos SET facturado=1, facturado_en_id=? WHERE id=?", (did, d["id"]))
    return did

# ----------------------------------------------------------------------------------------------- libros de IVA
TRIMESTRES = {"1": ("01-01", "03-31"), "2": ("04-01", "06-30"), "3": ("07-01", "09-30"), "4": ("10-01", "12-31")}

def periodo(anio, trimestre=None):
    if trimestre and str(trimestre) in TRIMESTRES:
        a, b = TRIMESTRES[str(trimestre)]
        return f"{anio}-{a}", f"{anio}-{b}"
    return f"{anio}-01-01", f"{anio}-12-31"

def libro(con, eid, clase, anio, trimestre=None):
    """Libro registro de facturas emitidas (F, incluidas rectificativas, y tiques no facturados) o recibidas (gastos).
    Una fila por tipo de IVA; retención y total solo en la primera fila de cada factura."""
    desde, hasta = periodo(anio, trimestre)
    if clase == "emitidas":
        sql = "SELECT * FROM documentos WHERE empresa_id=? AND (tipo='F' OR (tipo='M' AND COALESCE(facturado,0)=0))"
    else:
        sql = "SELECT * FROM documentos WHERE empresa_id=? AND tipo='G'"
    filas = []
    for d in con.execute(sql + " AND fecha BETWEEN ? AND ? ORDER BY fecha, serie, numero", (eid, desde, hasta)):
        d = dict(d)
        t = totales_cabecera(d)
        des = t["desglose"] or [{"base": D(0), "iva": D(0), "cuota_iva": D(0), "re": D(0), "cuota_re": D(0)}]
        ref = ""
        if d.get("rect_original_id"):
            o = con.execute("SELECT serie, numero FROM documentos WHERE id=?", (d["rect_original_id"],)).fetchone()
            ref = (o[0].strip() + o[1]) if o else ""
        for i, x in enumerate(des):
            filas.append({"fecha": d["fecha"], "fecha_operacion": d.get("fecha_operacion") or d["fecha"],
                          "numero": num_visible(d), "num_proveedor": d.get("num_factura_proveedor") or "",
                          "tipo": d["tipo"], "tipo_factura": d.get("vf_tipo_factura") or ("F2" if d["tipo"] == "M" else "F1"),
                          "rectifica": ref, "nif": d.get("nif") or "", "nombre": d.get("nombre_f") or "",
                          "base": x["base"], "iva": x["iva"], "cuota_iva": x["cuota_iva"], "re": x["re"], "cuota_re": x["cuota_re"],
                          "retencion": t["retencion"] if i == 0 else D(0), "total": t["total"] if i == 0 else D(0),
                          "primera": i == 0, "documento_id": d["id"], "serie": (d.get("serie") or "").strip(),
                          "num": d.get("numero") or "", "exento": bool(d.get("exento"))})
    return filas

def resumen_libro(filas):
    por_tipo = {}
    for f in filas:
        k = (f["iva"], f["re"])
        a = por_tipo.setdefault(k, {"iva": f["iva"], "re": f["re"], "base": D(0), "cuota_iva": D(0), "cuota_re": D(0)})
        a["base"] += f["base"]; a["cuota_iva"] += f["cuota_iva"]; a["cuota_re"] += f["cuota_re"]
    return {"por_tipo": sorted(por_tipo.values(), key=lambda a: (-a["iva"], -a["re"])),
            "base": sum((f["base"] for f in filas), D(0)), "cuota_iva": sum((f["cuota_iva"] for f in filas), D(0)),
            "cuota_re": sum((f["cuota_re"] for f in filas), D(0)), "retencion": sum((f["retencion"] for f in filas), D(0)),
            "total": sum((f["total"] for f in filas), D(0)), "facturas": len({f["documento_id"] for f in filas})}

CASILLAS_303 = {D(4): ("01", "02", "03"), D(10): ("04", "05", "06"), D(21): ("07", "08", "09")}

def resumen_303(con, eid, anio, trimestre):
    """Resumen APROXIMADO del modelo 303 (régimen general). Orientativo: lo revisa y presenta la gestoría."""
    em, rec = libro(con, eid, "emitidas", anio, trimestre), libro(con, eid, "recibidas", anio, trimestre)
    devengado, otros, re_dev = {}, [], []
    for a in resumen_libro(em)["por_tipo"]:
        iva = a["iva"]
        if iva in CASILLAS_303:
            cb, ct, cc = CASILLAS_303[iva]
            devengado.setdefault(iva, {"casillas": (cb, ct, cc), "iva": iva, "base": D(0), "cuota": D(0)})
            devengado[iva]["base"] += a["base"]; devengado[iva]["cuota"] += a["cuota_iva"]
        elif iva != 0:
            otros.append({"iva": iva, "base": a["base"], "cuota": a["cuota_iva"]})
        if a["cuota_re"]:
            re_dev.append({"re": a["re"], "base": a["base"], "cuota": a["cuota_re"]})
    sin_iva = sum((a["base"] for a in resumen_libro(em)["por_tipo"] if a["iva"] == 0), D(0))
    total_dev = sum((x["cuota"] for x in devengado.values()), D(0)) + sum((x["cuota"] for x in otros), D(0)) + \
                sum((x["cuota"] for x in re_dev), D(0))
    rr = resumen_libro(rec)
    deducible = rr["cuota_iva"]
    return {"anio": anio, "trimestre": trimestre, "devengado": [devengado[k] for k in sorted(devengado)], "otros": otros,
            "re": re_dev, "sin_iva": sin_iva, "c27": total_dev, "c28": rr["base"], "c29": deducible, "c45": deducible,
            "c46": total_dev - deducible, "ret_emitidas": resumen_libro(em)["retencion"], "ret_recibidas": rr["retencion"],
            "n_emitidas": resumen_libro(em)["facturas"], "n_recibidas": rr["facturas"]}

COLUMNAS_LIBRO = [("fecha", "Fecha expedición"), ("fecha_operacion", "Fecha operación"), ("numero", "Nº factura"),
                  ("num_proveedor", "Nº factura proveedor"), ("tipo_factura", "Tipo"), ("rectifica", "Rectifica a"),
                  ("nif", "NIF"), ("nombre", "Nombre / razón social"), ("base", "Base imponible"), ("iva", "% IVA"),
                  ("cuota_iva", "Cuota IVA"), ("re", "% RE"), ("cuota_re", "Cuota RE"), ("retencion", "Retención IRPF"),
                  ("total", "Total factura")]
NUMERICAS = {"base", "iva", "cuota_iva", "re", "cuota_re", "retencion", "total"}

def libro_csv(filas, clase):
    import csv, io
    cols = [c for c in COLUMNAS_LIBRO if not (clase == "emitidas" and c[0] == "num_proveedor")]
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\r\n")
    w.writerow([t for _, t in cols])
    for f in filas:
        fila = []
        for k, _ in cols:
            v = f[k]
            if k in NUMERICAS: v = format(dec(v).quantize(D("0.01")), "f").replace(".", ",")
            elif k.startswith("fecha"): v = _f(v)
            fila.append(v)
        w.writerow(fila)
    return ("\ufeff" + out.getvalue()).encode("utf-8")  # BOM: Excel en español lo abre con acentos bien

def libros_xlsx(con, eid, anio, trimestre=None):
    """Libros registro de IVA en Excel (ver excel.libros_iva)."""
    from .excel import libros_iva
    return libros_iva(con, eid, anio, trimestre)

# ------------------------------------------------------------------------------------------------ 0.0.5: buscador global
def _importe_buscado(q):
    """'1.234,50' / '1234.5' / '1234,50 €' -> Decimal, o None si el texto no es un importe."""
    import re
    from decimal import Decimal, InvalidOperation
    t = q.replace("€", "").replace(" ", "").strip()
    if not re.fullmatch(r"-?\d{1,3}(\.\d{3})*(,\d{1,2})?|-?\d+([.,]\d{1,2})?", t):
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None

def buscar(con, eid, q, limite=25):
    """Busca en la empresa: clientes y proveedores (nombre, NIF, código, población), documentos de cualquier tipo
    (número, cliente/proveedor, NIF, importe total, nº de factura del proveedor, concepto de las líneas) y productos
    (conceptos usados en las líneas). Sin distinguir mayúsculas. Devuelve un dict con listas."""
    q = (q or "").strip()
    res = {"q": q, "clientes": [], "proveedores": [], "documentos": [], "productos": [], "total": 0}
    if len(q) < 2 and not q.isdigit():
        return res
    like = f"%{q}%"
    for tabla in ("clientes", "proveedores"):
        res[tabla] = [dict(r) for r in con.execute(f"""SELECT id, codigo, nombre, nombre_f, nif, ciudad FROM {tabla}
            WHERE empresa_id=? AND (nombre LIKE ? OR nombre_f LIKE ? OR nif LIKE ? OR codigo = ? OR ciudad LIKE ?)
            ORDER BY nombre LIMIT ?""", (eid, like, like, like, q, like, limite))]
    importe = _importe_buscado(q)
    sql = """SELECT d.id, d.tipo, d.serie, d.numero, d.fecha, d.nombre_f, d.nif, d.total, d.pendiente FROM documentos d
             WHERE d.empresa_id=? AND (d.numero LIKE ? OR (d.serie || d.numero) LIKE ? OR (d.serie || '-' || d.numero) LIKE ?
             OR d.nombre_f LIKE ? OR d.nif LIKE ? OR d.num_factura_proveedor LIKE ?
             OR EXISTS (SELECT 1 FROM lineas l WHERE l.documento_id=d.id AND l.concepto LIKE ?)"""
    args = [eid, like, like, like, like, like, like, like]
    if importe is not None:
        sql += " OR ABS(CAST(d.total AS REAL) - ?) < 0.005"
        args.append(float(importe))
    sql += ") ORDER BY d.fecha DESC, d.id DESC LIMIT ?"
    args.append(limite)
    docs = []
    for r in con.execute(sql, args):
        r = dict(r)
        r["visible"] = num_visible(r)
        r["estado"] = estado_cobro(r)
        docs.append(r)
    res["documentos"] = docs
    res["productos"] = [dict(r) for r in con.execute("""SELECT l.concepto AS concepto, COUNT(DISTINCT l.documento_id) AS usos,
            MAX(d.fecha) AS ultima, (SELECT l2.precio FROM lineas l2 JOIN documentos d2 ON d2.id=l2.documento_id
              WHERE d2.empresa_id=? AND l2.concepto=l.concepto ORDER BY d2.fecha DESC, l2.id DESC LIMIT 1) AS precio
            FROM lineas l JOIN documentos d ON d.id=l.documento_id
            WHERE d.empresa_id=? AND l.concepto LIKE ? AND COALESCE(l.comentario,0)=0 AND TRIM(l.concepto)<>''
            GROUP BY l.concepto ORDER BY usos DESC, l.concepto LIMIT ?""", (eid, eid, like, limite))]
    res["total"] = sum(len(res[k]) for k in ("clientes", "proveedores", "documentos", "productos"))
    return res
