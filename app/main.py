"""Interfaz web local (FastAPI + Jinja2). Arranque: python -m app  ->  http://127.0.0.1:8765"""
import datetime, json, os, sys
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from .db import connect, db_path
from . import repo
from .repo import ErrorNegocio, AvisoNumeracion
from .calc import totales_cabecera, importe_linea, fmt_eur, dec, formato_pct, tipo_iva_valido, descuento_valido
from .fmt_pdf import render_pdf, render_recibos, titulo_documento
from .importer import NOMBRES_TIPO

def recursos():
    """Carpeta de plantillas: junto al código o, en el .exe de PyInstaller, dentro de sys._MEIPASS."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "app" / "templates" if (base / "app" / "templates").exists() else Path(__file__).parent / "templates"

app = FastAPI(title="ContFactu")
tpl = Jinja2Templates(directory=str(recursos()))
tpl.env.filters["eur"] = lambda v: fmt_eur(v or 0)
tpl.env.filters["fecha"] = lambda s: f"{s[8:10]}/{s[5:7]}/{s[:4]}" if s else ""
tpl.env.filters["num"] = repo.num_visible
tpl.env.filters["pct"] = formato_pct
from . import iconos, __version__ as VERSION
tpl.env.globals["ico"] = iconos.svg
tpl.env.globals["ICONO_TIPO"] = iconos.TIPO_ICONO
tpl.env.globals["VERSION"] = VERSION
tpl.env.globals["TIPOS"] = NOMBRES_TIPO
tpl.env.globals["PLURAL"] = {"F": "Facturas", "P": "Presupuestos", "A": "Albaranes", "G": "Gastos", "M": "Tiques", "D": "Pedidos"}
tpl.env.globals["MOTIVOS_R"] = repo.MOTIVOS_R

def db():
    return connect()

@app.exception_handler(ErrorNegocio)
async def error_negocio(request: Request, exc: ErrorNegocio):
    return tpl.TemplateResponse(request, "error.html", {"mensaje": str(exc), "volver": request.headers.get("referer") or "/"},
                                status_code=400)

def _emp(con, eid):
    e = repo.empresa(con, eid)
    if not e:
        raise HTTPException(404, "Empresa no encontrada")
    return e

def _doc(con, did):
    d, ls, ps = repo.documento(con, did)
    if not d:
        raise HTTPException(404, "Documento no encontrado")
    return d, ls, ps

def _n(v, defecto="0", campo=None, indice=None):
    v = (v or "").strip().replace(" ", "")
    if not v:
        return defecto
    if "," in v:  # formato español 1.234,56
        v = v.replace(".", "").replace(",", ".")
    try:
        dec(v)
    except Exception:
        raise ErrorNegocio(f"Número no válido: «{v}».", campo=campo, indice=indice)
    return v

def _err(ex):
    """Lo que la plantilla necesita para marcar un campo. Sin campo, el aviso va arriba, discreto."""
    return {"mensaje": str(ex), "campo": ex.campo, "indice": ex.indice}

# ------------------------------------------------------------------------------------------------ inicio
@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    con = db()
    es = repo.empresas(con)
    if not es:
        return RedirectResponse("/bienvenida", status_code=303)
    return tpl.TemplateResponse(request, "empresas.html", {"empresas": es})

@app.get("/bienvenida", response_class=HTMLResponse)
def bienvenida(request: Request):
    """Primera pantalla: importar de FactuCont o empezar desde cero."""
    return tpl.TemplateResponse(request, "bienvenida.html", {"hay": bool(repo.empresas(db())), "datos": str(db_path())})

# ------------------------------------------------------------------------------------------------ empresas desde cero
from . import altas
from .db import data_dir
tpl.env.globals["tabla_tipos"] = altas.tabla_tipos

def _x_empresa_error(f, eid=None):
    """Lo que el usuario escribió, para volver a mostrar el formulario con el error."""
    x = {k: f.get(k) for k in altas.CAMPOS_EMPRESA}
    x["_filas"] = list(zip(f.getlist("tipo_iva"), f.getlist("tipo_re")))
    if eid:
        x["id"] = eid
    return x

def _logo_ruta(e):
    if e and e.get("logo"):
        p = data_dir() / "logos" / os.path.basename(e["logo"])
        if p.exists():
            return p
    return None

async def _guardar_logo(con, eid, subido):
    """Guarda el logotipo (PNG/JPG, máx. 2 MB) en la carpeta de datos, nunca junto al programa."""
    if subido is None or not getattr(subido, "filename", ""):
        return
    ext = os.path.splitext(subido.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        raise ErrorNegocio("El logotipo debe ser una imagen PNG o JPG.", campo="logo")
    datos = await subido.read()
    if len(datos) > 2 * 1024 * 1024:
        raise ErrorNegocio("El logotipo es demasiado grande (máximo 2 MB).", campo="logo")
    try:
        from PIL import Image
        import io as _io
        Image.open(_io.BytesIO(datos)).verify()
    except Exception:
        raise ErrorNegocio("El archivo del logotipo no es una imagen válida.", campo="logo")
    carpeta = data_dir() / "logos"; carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"empresa_{eid}{'.jpg' if ext == '.jpeg' else ext}"
    for viejo in carpeta.glob(f"empresa_{eid}.*"):
        viejo.unlink()
    (carpeta / nombre).write_bytes(datos)
    altas.poner_logo(con, eid, nombre)

def _form_empresa(f):
    d = {k: f.get(k) for k in altas.CAMPOS_EMPRESA}
    if f.getlist("tipo_iva"):   # tabla editable de tipos de IVA y recargo de equivalencia
        d["ivas"], d["re_tasas"] = altas.tipos_desde_tabla(f.getlist("tipo_iva"), f.getlist("tipo_re"))
    return d

@app.get("/empresas/nueva", response_class=HTMLResponse)
def empresa_nueva(request: Request):
    con = db()
    e = {"codigo": altas.siguiente_codigo_empresa(con), "ivas": altas.IVAS_DEFECTO, "re_tasas": repo.RE_DEFECTO,
         "contador_inicial": 1, "serie_defecto": ""}
    return tpl.TemplateResponse(request, "empresa_form.html", {"x": e, "nueva": True, "anio": repo.hoy()[2:4],
                                                               "hay": bool(repo.empresas(con))})

@app.post("/empresas/nueva")
async def empresa_crear(request: Request):
    f = await request.form()
    con = db()
    try:
        with con:
            eid = altas.crear_empresa(con, _form_empresa(f))
            await _guardar_logo(con, eid, f.get("logo"))
    except ErrorNegocio as ex:
        x = _x_empresa_error(f)
        return tpl.TemplateResponse(request, "empresa_form.html", {"x": x, "nueva": True, "err": _err(ex), "anio": repo.hoy()[2:4],
                                                                   "hay": bool(repo.empresas(con))}, status_code=400)
    return RedirectResponse(f"/e/{eid}/documentos?tipo=F&ok=empresa", status_code=303)

@app.get("/e/{eid}/empresa", response_class=HTMLResponse)
def empresa_ver(request: Request, eid: int, ok: str = ""):
    con = db(); e = _emp(con, eid)
    x = dict(e)
    tiene_f = bool(con.execute("SELECT 1 FROM documentos WHERE empresa_id=? AND tipo='F'", (eid,)).fetchone())
    return tpl.TemplateResponse(request, "empresa_form.html", {"e": e, "x": x, "nueva": False, "ok": ok, "tiene_facturas": tiene_f,
                                                               "anio": repo.hoy()[2:4], "logo": _logo_ruta(e) is not None})

@app.post("/e/{eid}/empresa")
async def empresa_guardar(request: Request, eid: int):
    f = await request.form()
    con = db(); e = _emp(con, eid)
    try:
        with con:
            altas.actualizar_empresa(con, eid, _form_empresa(f))
            await _guardar_logo(con, eid, f.get("logo"))
            if f.get("quitar_logo") == "1":
                altas.poner_logo(con, eid, None)
    except ErrorNegocio as ex:
        return tpl.TemplateResponse(request, "empresa_form.html", {"e": e, "x": _x_empresa_error(f, eid), "nueva": False,
                                    "err": _err(ex), "anio": repo.hoy()[2:4], "logo": _logo_ruta(e) is not None}, status_code=400)
    return RedirectResponse(f"/e/{eid}/empresa?ok=1", status_code=303)

@app.get("/e/{eid}/logo")
def empresa_logo(eid: int):
    p = _logo_ruta(_emp(db(), eid))
    if not p:
        raise HTTPException(404)
    return Response(p.read_bytes(), media_type="image/png" if p.suffix == ".png" else "image/jpeg")

# ------------------------------------------------------------------------------------------------ fichas de clientes y proveedores
FICHAS = {"clientes": ("cliente", "Cliente", "Clientes"), "proveedores": ("proveedor", "Proveedor", "Proveedores")}

@app.get("/e/{eid}/{tabla}/nuevo", response_class=HTMLResponse)
def tercero_nuevo(request: Request, eid: int, tabla: str):
    if tabla not in FICHAS:
        raise HTTPException(404)
    con = db(); e = _emp(con, eid)
    return tpl.TemplateResponse(request, "tercero_form.html", {"e": e, "tabla": tabla, "F": FICHAS[tabla],
                                "x": {"codigo": altas.siguiente_codigo_tercero(con, eid, tabla)}, "nuevo": True})

@app.get("/e/{eid}/{tabla}/{tid:int}", response_class=HTMLResponse)
def tercero_ver(request: Request, eid: int, tabla: str, tid: int, ok: str = ""):
    if tabla not in FICHAS:
        raise HTTPException(404)
    con = db(); e = _emp(con, eid)
    r = con.execute(f"SELECT * FROM {tabla} WHERE id=? AND empresa_id=?", (tid, eid)).fetchone()
    if not r:
        raise HTTPException(404, "Ficha no encontrada")
    return tpl.TemplateResponse(request, "tercero_form.html", {"e": e, "tabla": tabla, "F": FICHAS[tabla], "x": dict(r), "nuevo": False, "ok": ok})

@app.post("/e/{eid}/{tabla}/guardar")
async def tercero_guardar(request: Request, eid: int, tabla: str):
    if tabla not in FICHAS:
        raise HTTPException(404)
    f = await request.form()
    con = db(); e = _emp(con, eid)
    tid = int(f["id"]) if f.get("id") else None
    try:
        with con:
            tid = altas.guardar_tercero(con, eid, tabla, dict(f), tid)
    except ErrorNegocio as ex:
        return tpl.TemplateResponse(request, "tercero_form.html", {"e": e, "tabla": tabla, "F": FICHAS[tabla], "x": dict(f),
                                    "nuevo": not tid, "err": _err(ex)}, status_code=400)
    if f.get("volver"):
        return RedirectResponse(f"/e/{eid}/{tabla}?ok=guardado", status_code=303)
    return RedirectResponse(f"/e/{eid}/{tabla}/{tid}?ok=guardado", status_code=303)

@app.get("/e/{eid}/proveedores", response_class=HTMLResponse)
def proveedores(request: Request, eid: int, q: str = "", ok: str = ""):
    con = db(); e = _emp(con, eid)
    like = f"%{q}%"
    rows = con.execute("""SELECT * FROM proveedores WHERE empresa_id=? AND (nombre LIKE ? OR nombre_f LIKE ? OR nif LIKE ? OR codigo LIKE ?
        OR ciudad LIKE ?) ORDER BY nombre""", (eid, like, like, like, like, like)).fetchall()
    return tpl.TemplateResponse(request, "clientes.html", {"e": e, "clientes": rows, "q": q, "tabla": "proveedores", "ok": ok})

@app.get("/e/{eid}/clientes", response_class=HTMLResponse)
def clientes(request: Request, eid: int, q: str = "", ok: str = ""):
    con = db(); e = _emp(con, eid)
    like = f"%{q}%"
    rows = con.execute("""SELECT * FROM clientes WHERE empresa_id=? AND (nombre LIKE ? OR nombre_f LIKE ? OR nif LIKE ? OR codigo LIKE ?
        OR ciudad LIKE ?) ORDER BY nombre""", (eid, like, like, like, like, like)).fetchall()
    return tpl.TemplateResponse(request, "clientes.html", {"e": e, "clientes": rows, "q": q, "tabla": "clientes", "ok": ok})

@app.get("/e/{eid}/documentos", response_class=HTMLResponse)
def documentos(request: Request, eid: int, tipo: str = "F", anio: str = "", q: str = "", ok: str = ""):
    con = db(); e = _emp(con, eid)
    if tipo not in NOMBRES_TIPO:
        raise HTTPException(404)
    anios = [r[0] for r in con.execute("SELECT DISTINCT substr(fecha,1,4) FROM documentos WHERE empresa_id=? AND tipo=? AND fecha IS NOT NULL ORDER BY 1 DESC", (eid, tipo))]
    if not anio and anios:
        anio = anios[0]
    sql = "SELECT * FROM documentos WHERE empresa_id=? AND tipo=?"
    args = [eid, tipo]
    if anio and anio != "todos":
        sql += " AND substr(fecha,1,4)=?"; args.append(anio)
    if q:
        sql += " AND (nombre_f LIKE ? OR numero LIKE ? OR nif LIKE ?)"; args += [f"%{q}%"] * 3
    rows = [dict(r) for r in con.execute(sql + " ORDER BY fecha DESC, serie DESC, numero DESC", args)]
    for r in rows:
        r["estado"] = repo.estado_cobro(r)
    suma = sum(dec(r["total"]) for r in rows)
    return tpl.TemplateResponse(request, "documentos.html", {"e": e, "docs": rows, "anios": anios, "anio": anio, "tipo": tipo, "q": q, "suma": suma, "ok": ok})

@app.get("/d/{did}", response_class=HTMLResponse)
def detalle(request: Request, did: int, ok: str = ""):
    con = db(); d, ls, ps = _doc(con, did)
    e = _emp(con, d["empresa_id"])
    for l in ls:
        l["importe"] = importe_linea(l)
    ver = con.execute("SELECT detalle FROM verificacion WHERE documento_id=?", (did,)).fetchall()
    rel = {}
    if d.get("rect_original_id"):
        rel["original"] = con.execute("SELECT * FROM documentos WHERE id=?", (d["rect_original_id"],)).fetchone()
    rel["rectificativas"] = con.execute("SELECT * FROM documentos WHERE rect_original_id=?", (did,)).fetchall()
    rel["origenes"] = con.execute("SELECT * FROM documentos WHERE facturado_en_id=?", (did,)).fetchall()
    if d.get("facturado_en_id"):
        rel["factura"] = con.execute("SELECT * FROM documentos WHERE id=?", (d["facturado_en_id"],)).fetchone()
    return tpl.TemplateResponse(request, "detalle.html", {
        "e": e, "d": d, "lineas": ls, "plazos": ps, "tot": totales_cabecera(d), "aviso": [v[0] for v in ver],
        "titulo": titulo_documento(d), "cobros": repo.cobros(con, did), "estado": repo.estado_cobro(d), "rel": rel,
        "ref_rect": repo.lineas_referencia_rectificativa(con, d), "hoy": repo.hoy(), "ok": ok,
        "recibos": repo.recibos_documento(con, did), "envios": correo.envios(con, did)})

def _pdf_documento(con, d, ls, ps):
    """(bytes del PDF, nombre de archivo) con el diseño importado de FactuCont o, si no hay, el diseño por defecto."""
    e = _emp(con, d["empresa_id"])
    fmt = repo.formato(con, d["empresa_id"], repo.CLASE_FORMATO.get(d["tipo"], "factura"))
    previas = repo.lineas_referencia_rectificativa(con, d)
    if fmt:
        data = render_pdf(fmt, e, d, ls, ps, lineas_previas=previas)
    else:   # empresa creada en ContFactu (o sin diseño importado): diseño propio por defecto
        from .fmt_pdf import render_pdf_defecto
        logo = _logo_ruta(e)
        data = render_pdf_defecto(e, d, ls, ps, logo=str(logo) if logo else None, lineas_previas=previas)
    return data, f"{titulo_documento(d).lower().replace(' ', '_')}_{repo.num_visible(d)}.pdf"

@app.get("/d/{did}/pdf")
def pdf(did: int):
    con = db(); d, ls, ps = _doc(con, did)
    data, nombre = _pdf_documento(con, d, ls, ps)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nombre}"'})

# ------------------------------------------------------------------------------------------------ correo electrónico
from . import correo

def _ctx_correo(con, e, c, **extra):
    return dict({"e": e, "c": c, "SEGURIDADES": correo.SEGURIDADES, "MARCADORES": correo.MARCADORES,
                 "hay_contrasena": bool(correo.leer_contrasena(e["id"]))}, **extra)

@app.get("/e/{eid}/correo", response_class=HTMLResponse)
def correo_ver(request: Request, eid: int, ok: str = ""):
    con = db(); e = _emp(con, eid)
    return tpl.TemplateResponse(request, "correo_config.html", _ctx_correo(con, e, correo.config(con, eid), ok=ok))

@app.post("/e/{eid}/correo", response_class=HTMLResponse)
async def correo_guardar(request: Request, eid: int):
    f = await request.form()
    con = db(); e = _emp(con, eid)
    datos = {k: f.get(k) for k in correo.CAMPOS}
    try:
        with con:
            correo.guardar_config(con, eid, datos)
        if f.get("borrar_contrasena") == "1":
            correo.guardar_contrasena(eid, "")
        elif f.get("contrasena"):
            correo.guardar_contrasena(eid, f.get("contrasena"))
        if f.get("accion") == "probar":
            c = correo.config(con, eid)
            correo.probar(c, correo.leer_contrasena(eid))
            return tpl.TemplateResponse(request, "correo_config.html", _ctx_correo(con, e, c, prueba_ok=True))
    except correo.ErrorCorreo as ex:
        c = dict(correo.config(con, eid), **{k: v for k, v in datos.items() if v is not None})
        return tpl.TemplateResponse(request, "correo_config.html", _ctx_correo(con, e, c, error=str(ex)),
                                    status_code=200 if f.get("accion") == "probar" else 400)
    return RedirectResponse(f"/e/{eid}/correo?ok=1", status_code=303)

def _ctx_envio(con, d, ls, ps, **extra):
    e = _emp(con, d["empresa_id"])
    c = correo.config(con, e["id"])
    v = correo.valores_documento(e, d, ps, titulo_documento(d), repo.num_visible(d))
    ctx = {"e": e, "d": d, "c": c, "titulo": titulo_documento(d), "envios": correo.envios(con, d["id"]),
           "para": correo.correo_cliente(con, d), "copia": c.get("copia") or "",
           "asunto": correo.rellenar(c["asunto"], v), "cuerpo": correo.rellenar(c["cuerpo"], v),
           "adjunto": f"{titulo_documento(d).lower().replace(' ', '_')}_{repo.num_visible(d)}.pdf",
           "hay_contrasena": bool(correo.leer_contrasena(e["id"])) or not c.get("usuario")}
    ctx.update(extra)
    return ctx

@app.get("/d/{did}/enviar", response_class=HTMLResponse)
def enviar_vista(request: Request, did: int):
    """Vista previa del correo. No se envía nada hasta pulsar «Enviar» en esta pantalla."""
    con = db(); d, ls, ps = _doc(con, did)
    return tpl.TemplateResponse(request, "enviar.html", _ctx_envio(con, d, ls, ps))

@app.post("/d/{did}/enviar", response_class=HTMLResponse)
async def enviar_documento(request: Request, did: int):
    f = await request.form()
    con = db(); d, ls, ps = _doc(con, did)
    para, copia = (f.get("para") or "").strip(), (f.get("copia") or "").strip()
    asunto, cuerpo = (f.get("asunto") or "").strip(), (f.get("cuerpo") or "").replace("\r\n", "\n")
    if f.get("confirmar") != "1":
        raise ErrorNegocio("Para enviar el correo hay que pulsar «Enviar» en la vista previa.")
    c = correo.config(con, d["empresa_id"])
    data, nombre = _pdf_documento(con, d, ls, ps)
    try:
        if not asunto:
            raise correo.ErrorCorreo("El asunto está vacío.")
        msg = correo.construir(c, para, copia, asunto, cuerpo, nombre, data)
        correo.enviar(c, correo.leer_contrasena(d["empresa_id"]), msg)
    except correo.ErrorCorreo as ex:
        with con:
            correo.registrar(con, did, para, copia, asunto, nombre, error=str(ex))
        return tpl.TemplateResponse(request, "enviar.html", _ctx_envio(con, d, ls, ps, para=para, copia=copia, asunto=asunto,
                                    cuerpo=cuerpo, error=str(ex)), status_code=400)
    with con:
        correo.registrar(con, did, para, copia, asunto, nombre)
    return RedirectResponse(f"/d/{did}?ok=enviado", status_code=303)

# ------------------------------------------------------------------------------------------------ alta / edición
def _form_contexto(con, e, tipo, d=None, lineas=None, aviso_legal=None, pre=None, nuevo=None, con_re=None, err=None):
    tabla = "proveedores" if tipo == "G" else "clientes"
    terceros = [dict(c) for c in con.execute(f"SELECT * FROM {tabla} WHERE empresa_id=? ORDER BY nombre", (e["id"],))]
    hoy = repo.hoy()
    serie = (e.get("serie_defecto") or "") if tipo == "F" else ""
    es_nuevo = (d is None) if nuevo is None else nuevo
    sig = repo.siguiente_numero(con, e["id"], tipo, serie, hoy) if es_nuevo else None
    ls = [{k: l.get(k) for k in ("codigo", "concepto", "cantidad", "precio", "descuento", "iva", "comentario")} for l in (lineas or [])]
    if con_re is None:
        con_re = d is not None and repo._con_re(d)
    return {"e": e, "tipo": tipo, "d": d or dict({"fecha": hoy, "descuento": "0", "retencion": "0"}, **(pre or {})), "nuevo": es_nuevo,
            "terceros_json": json.dumps([{k: c.get(k) for k in ("codigo", "nombre", "nombre_f", "direccion", "direccion_f", "ciudad",
                                         "ciudad_f", "nif", "forma_pago", "recargo", "retencion")} for c in terceros], ensure_ascii=False),
            "terceros": terceros, "lineas_json": json.dumps(ls, ensure_ascii=False), "siguiente": sig,
            "con_re": con_re, "aviso_legal": aviso_legal, "err": err,
            "serie_defecto": serie, "ivas": altas.ivas_de(e),
            "tasas_re_json": json.dumps({k: float(v) for k, v in altas.tasas_re_de(e).items()})}

def _lineas_crudas(f):
    """Filas tal como se enviaron, para volver a pintarlas si hay un error. El índice coincide con el del formulario."""
    res = []
    for i in range(int(f.get("n_lineas", 0) or 0)):
        precio = f.get(f"precio_{i}") or ""
        res.append({"codigo": f.get(f"codigo_{i}") or "", "concepto": f.get(f"concepto_{i}") or "",
                    "cantidad": f.get(f"cantidad_{i}") or "", "precio": precio,
                    "descuento": f.get(f"descuento_{i}") or "", "iva": f.get(f"iva_{i}") or "",
                    "comentario": not precio.strip()})
    return res

def _cabecera_cruda(f, did=None):
    d = {k: (f.get(k) or "") for k in ("fecha", "serie", "nombre_f", "direccion_f", "ciudad_f", "nif", "forma_pago",
                                       "cliente_codigo", "num_factura_proveedor", "domiciliacion", "ccc", "descuento", "retencion")}
    d["iva_incluido"] = 1 if f.get("iva_incluido") == "1" else 0
    if did:
        d["id"] = did
    return d

@app.get("/e/{eid}/nueva")
def nueva_compat(eid: int, cliente: str = ""):
    from urllib.parse import quote
    return RedirectResponse(f"/e/{eid}/nuevo/F" + (f"?cliente={quote(cliente)}" if cliente else ""), status_code=303)

@app.get("/e/{eid}/nuevo/{tipo}", response_class=HTMLResponse)
def nuevo(request: Request, eid: int, tipo: str):
    con = db(); e = _emp(con, eid)
    if tipo not in NOMBRES_TIPO:
        raise HTTPException(404)
    pre = None
    cliente = request.query_params.get("cliente")
    if cliente:   # «facturar» desde la ficha o la lista: cliente/proveedor ya elegido
        tabla = "proveedores" if tipo == "G" else "clientes"
        c = con.execute(f"SELECT * FROM {tabla} WHERE empresa_id=? AND codigo=?", (eid, cliente)).fetchone()
        if c:
            c = dict(c)
            pre = {"cliente_codigo": c["codigo"], "nombre_f": c.get("nombre_f") or c["nombre"], "direccion_f": c.get("direccion_f") or c.get("direccion"),
                   "ciudad_f": c.get("ciudad_f") or c.get("ciudad"), "nif": c.get("nif"), "forma_pago": c.get("forma_pago"),
                   "descuento": c.get("descuento") or "0", "retencion": c.get("retencion") or "0"}
    return tpl.TemplateResponse(request, "documento_form.html", _form_contexto(con, e, tipo, pre=pre))

@app.get("/d/{did}/editar", response_class=HTMLResponse)
def editar(request: Request, did: int):
    con = db(); d, ls, _ = _doc(con, did)
    e = _emp(con, d["empresa_id"])
    aviso = None
    if d["tipo"] == "F":
        aviso = ("Está modificando una factura ya emitida. Solo debe hacerlo si todavía no la ha entregado al cliente "
                 "ni la ha declarado. Si ya la tiene el cliente, lo correcto es emitir una factura rectificativa.")
    return tpl.TemplateResponse(request, "documento_form.html", _form_contexto(con, e, d["tipo"], d, ls, aviso))

def _leer_form(f):
    lineas = []
    for i in range(int(f.get("n_lineas", 0) or 0)):
        concepto = (f.get(f"concepto_{i}") or "").strip()
        precio = (f.get(f"precio_{i}") or "").strip()
        if not concepto and not precio:
            continue
        coment = not precio
        try:
            iva = "21" if coment or not (f.get(f"iva_{i}") or "").strip() else tipo_iva_valido(f.get(f"iva_{i}"))
        except ValueError as ex:
            raise ErrorNegocio(str(ex), campo="iva", indice=i)
        try:
            dto = "" if coment else descuento_valido(f.get(f"descuento_{i}"))
        except ValueError as ex:
            raise ErrorNegocio(str(ex), campo="descuento", indice=i)
        lineas.append({"codigo": f.get(f"codigo_{i}"), "concepto": concepto,
                       "cantidad": _n(f.get(f"cantidad_{i}"), "1", campo="cantidad", indice=i),
                       "precio": "" if coment else _n(precio, campo="precio", indice=i),
                       "descuento": dto, "iva": iva, "comentario": coment})
    datos = {k: (f.get(k) or "").strip() or None for k in ("fecha", "serie", "nombre_f", "direccion_f", "ciudad_f", "nif", "forma_pago",
                                                          "cliente_codigo", "num_factura_proveedor", "domiciliacion", "ccc")}
    try:
        datos["descuento"] = descuento_valido(f.get("descuento"))
    except ValueError as ex:
        raise ErrorNegocio(str(ex), campo="descuento")
    datos["retencion"] = _n(f.get("retencion"), campo="retencion")
    datos["re"] = f.get("re") == "1"
    datos["iva_incluido"] = f.get("iva_incluido") == "1"
    if not datos.get("nombre_f"):
        raise ErrorNegocio("Falta el nombre del cliente o proveedor.", campo="nombre_f")
    return datos, lineas

def _documento_con_error(request, con, e, tipo, f, ex, did=None, rectifica=None, modo=None):
    ctx = _form_contexto(con, e, tipo, _cabecera_cruda(f, did), _lineas_crudas(f), nuevo=did is None and rectifica is None,
                         con_re=f.get("re") == "1", err=_err(ex))
    if rectifica is not None:
        ctx.update(rectifica=rectifica, modo=modo or "I", nuevo=True,
                   siguiente=repo.siguiente_numero(con, e["id"], "F", repo.SERIE_RECTIFICATIVA, repo.hoy()))
    return tpl.TemplateResponse(request, "documento_form.html", ctx, status_code=400)

@app.post("/e/{eid}/guardar/{tipo}")
async def guardar(request: Request, eid: int, tipo: str):
    con = db(); e = _emp(con, eid)
    f = await request.form()
    did = int(f.get("id")) if f.get("id") else None
    try:
        datos, lineas = _leer_form(f)
        if did:
            datos.pop("serie", None)
        with con:
            did = repo.guardar_documento(con, eid, tipo, datos, lineas, did)
    except ErrorNegocio as ex:
        return _documento_con_error(request, con, e, tipo, f, ex, did=int(f.get("id")) if f.get("id") else None)
    return RedirectResponse(f"/d/{did}?ok=guardado", status_code=303)

@app.post("/e/{eid}/nueva")  # compatibilidad con la primera versión
async def crear(request: Request, eid: int):
    return await guardar(request, eid, "F")

# ------------------------------------------------------------------------------------------------ borrar
@app.get("/d/{did}/borrar", response_class=HTMLResponse)
def borrar_confirmar(request: Request, did: int):
    con = db(); d, _, _ = _doc(con, did)
    return tpl.TemplateResponse(request, "borrar.html", {"e": _emp(con, d["empresa_id"]), **repo.info_borrado(con, did)})

@app.post("/d/{did}/borrar")
async def borrar(request: Request, did: int):
    f = await request.form()
    if f.get("confirmar") != "1":
        raise ErrorNegocio("Debe confirmar el borrado.")
    con = db(); d, _, _ = _doc(con, did)
    with con:
        repo.borrar_documento(con, did, forzar=f.get("forzar") == "1")
    return RedirectResponse(f"/e/{d['empresa_id']}/documentos?tipo={d['tipo']}&anio={(d['fecha'] or '')[:4]}", status_code=303)

# ------------------------------------------------------------------------------------------------ rectificativas
@app.get("/d/{did}/rectificar", response_class=HTMLResponse)
def rectificar_form(request: Request, did: int, modo: str = "I"):
    con = db(); d, ls, _ = _doc(con, did)
    if d["tipo"] != "F":
        raise ErrorNegocio("Solo se pueden rectificar facturas.")
    e = _emp(con, d["empresa_id"])
    modo = "S" if modo == "S" else "I"
    lineas = repo.lineas_por_defecto_rectificativa(con, did, modo)
    ctx = _form_contexto(con, e, "F", dict(d, fecha=repo.hoy()), lineas)
    ctx.update(rectifica=d, modo=modo, nuevo=True,
               siguiente=repo.siguiente_numero(con, e["id"], "F", repo.SERIE_RECTIFICATIVA, repo.hoy()))
    return tpl.TemplateResponse(request, "documento_form.html", ctx)

@app.post("/d/{did}/rectificar")
async def rectificar(request: Request, did: int):
    con = db(); d, _, _ = _doc(con, did)
    e = _emp(con, d["empresa_id"])
    f = await request.form()
    try:
        datos, lineas = _leer_form(f)
        with con:
            nid = repo.crear_rectificativa(con, did, f.get("rect_tipo"), f.get("rect_motivo"), f.get("codigo_r") or "R4",
                                           datos.get("fecha"), lineas, cabecera=datos)
    except ErrorNegocio as ex:
        return _documento_con_error(request, con, e, "F", f, ex, rectifica=d, modo="S" if f.get("rect_tipo") == "S" else "I")
    return RedirectResponse(f"/d/{nid}?ok=rectificativa", status_code=303)

# ------------------------------------------------------------------------------------------------ cobros y recibos
@app.post("/d/{did}/cobro")
async def cobro(request: Request, did: int):
    f = await request.form()
    con = db(); _doc(con, did)
    with con:
        repo.registrar_cobro(con, did, _n(f.get("importe")), f.get("fecha") or None, f.get("forma") or "", f.get("nota") or "",
                             int(f.get("plazo_id")) if f.get("plazo_id") else None)
    return RedirectResponse(f"/d/{did}?ok=cobro", status_code=303)

@app.post("/cobro/{cid}/anular")
def anular(cid: int):
    con = db()
    with con:
        did = repo.anular_cobro(con, cid)
    return RedirectResponse(f"/d/{did}?ok=anulado", status_code=303)

@app.get("/d/{did}/recibos")
def recibos(did: int, plazo: int = 0):
    con = db(); d, _, _ = _doc(con, did)
    e = _emp(con, d["empresa_id"])
    rs = repo.recibos_documento(con, did)
    if plazo:
        rs = [r for r in rs if r[0]["id"] == plazo]
    if not rs:
        raise ErrorNegocio("Este documento no tiene vencimientos para imprimir recibos.")
    data = render_recibos(repo.formato(con, e["id"], "recibo"), e, d, rs)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="recibos_{repo.num_visible(d)}.pdf"'})

@app.get("/e/{eid}/pendientes", response_class=HTMLResponse)
def pendientes(request: Request, eid: int):
    con = db(); e = _emp(con, eid)
    ps = repo.pendientes(con, eid)
    return tpl.TemplateResponse(request, "pendientes.html", {"e": e, "docs": ps, "suma": sum(dec(p["pendiente"]) for p in ps),
                                                             "vencido": sum(dec(p["pendiente"]) for p in ps if p["vencido"]), "hoy": repo.hoy()})

# ------------------------------------------------------------------------------------------------ facturar
@app.get("/e/{eid}/facturar", response_class=HTMLResponse)
def facturar_form(request: Request, eid: int, tipo: str = "A", cliente: str = ""):
    con = db(); e = _emp(con, eid)
    docs = repo.facturables(con, eid, tipo)
    clientes = sorted({d["nombre_f"] or "" for d in docs})
    if cliente:
        docs = [d for d in docs if (d["nombre_f"] or "") == cliente]
    return tpl.TemplateResponse(request, "facturar.html", {"e": e, "tipo": tipo, "docs": docs, "clientes": clientes,
                                                           "cliente": cliente, "hoy": repo.hoy()})

@app.post("/e/{eid}/facturar")
async def facturar(request: Request, eid: int):
    f = await request.form()
    ids = [int(x) for x in f.getlist("ids")]
    con = db(); _emp(con, eid)
    with con:
        did = repo.facturar(con, ids, f.get("fecha") or None, (f.get("serie") or "").strip())
    return RedirectResponse(f"/d/{did}?ok=facturado", status_code=303)

# ------------------------------------------------------------------------------------------------ libros de IVA
@app.get("/e/{eid}/libros", response_class=HTMLResponse)
def libros(request: Request, eid: int, anio: str = "", t: str = ""):
    con = db(); e = _emp(con, eid)
    anios = [r[0] for r in con.execute("SELECT DISTINCT substr(fecha,1,4) FROM documentos WHERE empresa_id=? AND tipo IN ('F','G','M') AND fecha IS NOT NULL ORDER BY 1 DESC", (eid,))]
    anio = anio or (anios[0] if anios else str(datetime.date.today().year))
    em, rc = repo.libro(con, eid, "emitidas", anio, t or None), repo.libro(con, eid, "recibidas", anio, t or None)
    return tpl.TemplateResponse(request, "libros.html", {"e": e, "anios": anios, "anio": anio, "t": t, "emitidas": em, "recibidas": rc,
        "r_em": repo.resumen_libro(em), "r_rc": repo.resumen_libro(rc), "m303": repo.resumen_303(con, eid, anio, t) if t else None})

@app.get("/e/{eid}/libros.xlsx")
def libros_xlsx(eid: int, anio: str, t: str = ""):
    con = db(); e = _emp(con, eid)
    data = repo.libros_xlsx(con, eid, anio, t or None)
    nombre = f"libros_iva_{e['codigo']}_{anio}{'_' + t + 'T' if t else ''}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

from . import excel

def _xlsx(data, nombre):
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

@app.get("/e/{eid}/documentos.xlsx")
def documentos_xlsx(eid: int, tipo: str = "F", anio: str = "", q: str = ""):
    con = db(); e = _emp(con, eid)
    if tipo not in NOMBRES_TIPO:
        raise HTTPException(404)
    nombre = {"F": "facturas", "P": "presupuestos", "A": "albaranes", "G": "gastos", "M": "tiques", "D": "pedidos"}[tipo]
    return _xlsx(excel.documentos(con, eid, tipo, anio, q), f"{nombre}_{e['codigo']}{'_' + anio if anio and anio != 'todos' else ''}.xlsx")

@app.get("/e/{eid}/pendientes.xlsx")
def pendientes_xlsx(eid: int):
    con = db(); e = _emp(con, eid)
    return _xlsx(excel.pendientes(con, eid), f"cobros_pendientes_{e['codigo']}_{repo.hoy()}.xlsx")

@app.get("/e/{eid}/{tabla}.xlsx")
def terceros_xlsx(eid: int, tabla: str):
    if tabla not in ("clientes", "proveedores"):
        raise HTTPException(404)
    con = db(); e = _emp(con, eid)
    return _xlsx(excel.terceros(con, eid, tabla), f"{tabla}_{e['codigo']}.xlsx")

@app.get("/e/{eid}/libro_{clase}.csv")
def libro_csv(eid: int, clase: str, anio: str, t: str = ""):
    if clase not in ("emitidas", "recibidas"):
        raise HTTPException(404)
    con = db(); e = _emp(con, eid)
    data = repo.libro_csv(repo.libro(con, eid, clase, anio, t or None), clase)
    nombre = f"libro_{clase}_{e['codigo']}_{anio}{'_' + t + 'T' if t else ''}.csv"
    return Response(data, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

# ------------------------------------------------------------------------------------------------ verificación
@app.get("/e/{eid}/verificacion", response_class=HTMLResponse)
def verificacion(request: Request, eid: int):
    con = db(); e = _emp(con, eid)
    rows = con.execute("SELECT v.*, d.fecha FROM verificacion v LEFT JOIN documentos d ON d.id=v.documento_id WHERE v.empresa_id=? ORDER BY d.fecha", (eid,)).fetchall()
    return tpl.TemplateResponse(request, "verificacion.html", {"e": e, "rows": rows})

# ------------------------------------------------------------------------------------------------ asistente
# No se sugiere ninguna ruta: los datos válidos pueden estar en otro equipo (p. ej. un equipo antiguo o una máquina virtual)
# y una instalación local de FactuCont puede estar desactualizada. El usuario elige siempre el origen.

@app.get("/asistente", response_class=HTMLResponse)
def asistente(request: Request):
    return tpl.TemplateResponse(request, "asistente.html", {"ruta": "", "datos": str(db_path()),
                                                            "hay": bool(repo.empresas(db())), "resultado": None})

@app.post("/importar", response_class=HTMLResponse)
async def importar(request: Request):
    import shutil, tempfile
    from .importer import importar_fc5
    from .origen import preparar, OrigenError
    f = await request.form()
    ruta = (f.get("ruta") or "").strip().strip('"')
    subido, tmp_subida = f.get("archivo"), None
    try:
        if subido is not None and getattr(subido, "filename", ""):
            nombre = os.path.basename(subido.filename)
            if not nombre.lower().endswith((".zip", ".rar")):
                raise OrigenError("El archivo debe ser .zip o .rar.")
            tmp_subida = tempfile.mkdtemp(prefix="contfactu_sub_")
            ruta_arch = os.path.join(tmp_subida, nombre)
            with open(ruta_arch, "wb") as out:
                shutil.copyfileobj(subido.file, out)
            fc5, tmp = preparar(ruta_arch)
            mostrado = nombre
        else:
            fc5, tmp = preparar(ruta)
            mostrado = ruta
    except OrigenError as e:
        if tmp_subida: shutil.rmtree(tmp_subida, ignore_errors=True)
        raise ErrorNegocio(str(e))
    try:
        con = db()
        with con:
            res = importar_fc5(con, fc5)
    finally:
        for t in (tmp, tmp_subida):
            if t: shutil.rmtree(t, ignore_errors=True)
    return tpl.TemplateResponse(request, "asistente.html", {"ruta": mostrado, "datos": str(db_path()), "hay": True, "resultado": res})

# ------------------------------------------------------------------------------------------------ avisos al arrancar
# «Sesión» = mientras ContFactu está abierto (un proceso). Lo que se oculta vuelve a salir la próxima vez que se abra.
SESION = {"alertas_ocultas": set(), "copia_oculta": False, "restaurar": {}}

def avisos(request, e=None):
    """Avisos de la parte superior: cobros vencidos/próximos de la empresa y recordatorio de copia de seguridad."""
    res = {}
    try:
        con = db()
        if e and e.get("id") not in SESION["alertas_ocultas"] and not request.url.path.startswith(f"/e/{e['id']}/pendientes"):
            a = repo.alertas_cobro(con, e["id"])
            if a["hay"]:
                res["cobros"] = a
        if not SESION["copia_oculta"] and not request.url.path.startswith("/copias") and copias.necesita_aviso(con):
            res["copia"] = {"dias": copias.dias_desde_ultima(con), "plazo": copias.dias_aviso(con)}
        if copias.auto_activada(con) and ajuste(con, "copia_auto_aviso"):   # solo si el usuario activó las automáticas
            res["copia_auto_aviso"] = ajuste(con, "copia_auto_aviso")
    except Exception:   # un aviso nunca debe impedir trabajar
        pass
    return res

tpl.env.globals["avisos_inicio"] = avisos

@app.post("/e/{eid}/alertas/ocultar")
async def alertas_ocultar(request: Request, eid: int):
    SESION["alertas_ocultas"].add(eid)
    return RedirectResponse(request.headers.get("referer") or f"/e/{eid}/documentos?tipo=F", status_code=303)

@app.post("/copias/recordar-luego")
async def copia_recordar_luego(request: Request):
    SESION["copia_oculta"] = True
    return RedirectResponse(request.headers.get("referer") or "/", status_code=303)

@app.post("/copias/no-recordar")
async def copia_no_recordar(request: Request):
    """Casilla «No volver a recordar» del aviso de copia: se puede volver a activar en Copias > Recordatorio."""
    f = await request.form()
    con = db()
    if f.get("no_recordar") == "1":
        with con:
            poner_ajuste(con, "copia_no_recordar", "1")
    SESION["copia_oculta"] = True
    return RedirectResponse(request.headers.get("referer") or "/", status_code=303)

@app.post("/copias/aviso-auto/visto")
async def copia_aviso_auto_visto(request: Request):
    con = db()
    with con:
        poner_ajuste(con, "copia_auto_aviso", None)
    return RedirectResponse(request.headers.get("referer") or "/", status_code=303)

# ------------------------------------------------------------------------------------------------ copias de seguridad
from . import copias
from .db import ajuste, poner_ajuste

def _ctx_copias(con, **extra):
    auto = copias.carpeta_automaticas()
    carpeta = ajuste(con, "copia_carpeta") or str(copias.carpeta_defecto())
    return dict({"carpeta": carpeta, "ultima": ajuste(con, "copia_ultima"),
                 "ultima_archivo": ajuste(con, "copia_ultima_archivo"), "dias": copias.dias_aviso(con),
                 "no_recordar": ajuste(con, "copia_no_recordar") == "1",
                 "auto_on": copias.auto_activada(con), "auto_cuando": copias.auto_cuando(con), "CUANDO": copias.CUANDO,
                 "auto_carpeta": str(copias.auto_carpeta(con)), "auto_conservar": copias.auto_conservar(con),
                 "auto_ultima": ajuste(con, "copia_auto_ultima"), "auto_ultima_archivo": ajuste(con, "copia_auto_ultima_archivo"),
                 "copias_lista": copias.listar_copias(carpeta, copias.auto_carpeta(con), auto)[:60],
                 "carpeta_auto": str(auto), "datos": str(data_dir()), "hay": bool(repo.empresas(con))}, **extra)

@app.get("/copias", response_class=HTMLResponse)
def copias_ver(request: Request, ok: str = "", archivo: str = "", aviso: str = ""):
    con = db()
    return tpl.TemplateResponse(request, "copias.html", _ctx_copias(con, ok=ok, archivo=archivo, aviso=aviso))

@app.post("/copias/crear", response_class=HTMLResponse)
async def copias_crear(request: Request):
    f = await request.form()
    con = db()
    try:
        ruta = copias.crear_copia(con, f.get("carpeta"))
    except copias.ErrorCopia as ex:
        return tpl.TemplateResponse(request, "copias.html", _ctx_copias(con, error=str(ex), carpeta=f.get("carpeta") or ""), status_code=400)
    SESION["copia_oculta"] = False
    from urllib.parse import quote
    return RedirectResponse(f"/copias?ok=copia&archivo={quote(str(ruta))}", status_code=303)

@app.post("/copias/ajustes")
async def copias_ajustes(request: Request):
    f = await request.form()
    con = db()
    try:
        n = int(f.get("dias") or 0); assert 0 <= n <= 365
    except (ValueError, AssertionError):
        raise ErrorNegocio("Los días del recordatorio deben ser un número entre 0 (no recordar) y 365.")
    with con:
        poner_ajuste(con, "copia_dias", n)
        poner_ajuste(con, "copia_no_recordar", "1" if f.get("no_recordar") == "1" else None)
        if (f.get("carpeta") or "").strip():
            poner_ajuste(con, "copia_carpeta", f.get("carpeta").strip().strip('"'))
    return RedirectResponse("/copias?ok=ajustes", status_code=303)

@app.post("/copias/automaticas", response_class=HTMLResponse)
async def copias_automaticas_ajustes(request: Request):
    """Copias automáticas (0.0.5). Desactivadas por defecto: solo se hacen si el usuario marca la casilla."""
    f = await request.form()
    con = db()
    activar = f.get("activar") == "1"
    cuando = f.get("cuando") or "cerrar"
    carpeta = (f.get("carpeta") or "").strip().strip('"')
    try:
        if cuando not in copias.CUANDO:
            raise ErrorNegocio("Elija cuándo hacer las copias automáticas.")
        try:
            n = int(f.get("conservar") or copias.CONSERVAR_PROGRAMADAS); assert 1 <= n <= 200
        except (ValueError, AssertionError):
            raise ErrorNegocio("El número de copias que se guardan debe estar entre 1 y 200.")
        if carpeta and not Path(carpeta).is_absolute():
            raise ErrorNegocio(f"Indique una carpeta completa (p. ej. {copias.carpeta_defecto()}).")
    except ErrorNegocio as ex:
        return tpl.TemplateResponse(request, "copias.html", _ctx_copias(con, error=str(ex)), status_code=400)
    aviso = ""
    if activar and carpeta and not copias._carpeta_usable(carpeta):
        aviso = "&aviso=carpeta"
    with con:
        poner_ajuste(con, "copia_auto", "1" if activar else "0")
        poner_ajuste(con, "copia_auto_cuando", cuando)
        poner_ajuste(con, "copia_auto_conservar", n)
        poner_ajuste(con, "copia_auto_carpeta", carpeta or None)
        poner_ajuste(con, "copia_auto_aviso", None)
    return RedirectResponse(f"/copias?ok=auto{aviso}", status_code=303)

@app.post("/copias/restaurar/revisar", response_class=HTMLResponse)
async def copias_revisar(request: Request):
    """Primer paso de la restauración: comprobar el .zip y enseñar qué contiene. Todavía no se toca nada."""
    import secrets, shutil, tempfile
    f = await request.form()
    con = db()
    subido = f.get("archivo")
    ruta = (f.get("ruta") or "").strip().strip('"')
    if subido is not None and getattr(subido, "filename", ""):
        if not subido.filename.lower().endswith(".zip"):
            return tpl.TemplateResponse(request, "copias.html", _ctx_copias(con, error="La copia debe ser un archivo .zip."), status_code=400)
        tmp = tempfile.mkdtemp(prefix="contfactu_subida_")
        ruta = os.path.join(tmp, os.path.basename(subido.filename))
        with open(ruta, "wb") as out:
            shutil.copyfileobj(subido.file, out)
        mostrado = subido.filename
    else:
        mostrado = ruta
    try:
        if not ruta:
            raise copias.ErrorCopia("Elija el archivo .zip de la copia que quiere restaurar.")
        info = copias.leer_copia(ruta)
    except copias.ErrorCopia as ex:
        return tpl.TemplateResponse(request, "copias.html", _ctx_copias(con, error=str(ex)), status_code=400)
    token = secrets.token_urlsafe(16)
    SESION["restaurar"][token] = ruta
    return tpl.TemplateResponse(request, "restaurar.html", {"info": info, "token": token, "mostrado": mostrado,
                                                             "actual": copias._recuento(db_path()) if db_path().exists() else None,
                                                             "hay": bool(repo.empresas(con))})

@app.post("/copias/restaurar", response_class=HTMLResponse)
async def copias_restaurar(request: Request):
    f = await request.form()
    ruta = SESION["restaurar"].get(f.get("token") or "")
    if not ruta:
        raise ErrorNegocio("La restauración ha caducado: vuelva a elegir la copia.")
    if f.get("confirmar") != "1":
        raise ErrorNegocio("Para restaurar hay que marcar la casilla de confirmación.")
    try:
        info, previa = copias.restaurar(ruta)
    except copias.ErrorCopia as ex:
        raise ErrorNegocio(str(ex))
    SESION["restaurar"].pop(f.get("token"), None)
    if os.path.basename(os.path.dirname(ruta)).startswith("contfactu_subida_"):
        import shutil
        shutil.rmtree(os.path.dirname(ruta), ignore_errors=True)
    SESION["alertas_ocultas"].clear()
    try:
        from . import movil
        movil.sincronizar()   # la copia puede traer la opción activada o apagada; el puerto tiene que coincidir
    except Exception:
        pass
    return tpl.TemplateResponse(request, "restaurado.html", {"info": info, "previa": str(previa) if previa else None,
                                                             "hay": bool(repo.empresas(db()))})

# ------------------------------------------------------------------------------------------------ 0.2.0: acceso desde el móvil (opcional, desactivado de origen)
def _solo_este_equipo(request):
    """La pantalla de ajustes no se sirve más que en local. Un formulario de otra web tampoco puede activarla."""
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "testclient"):
        return False
    origen = request.headers.get("origin")
    if origen:
        from urllib.parse import urlparse
        if urlparse(origen).hostname not in ("127.0.0.1", "localhost", "::1"):
            return False
    if (request.headers.get("sec-fetch-site") or "").lower() == "cross-site":
        return False
    return True

def _rechazo_remoto():
    return Response("Esta pantalla solo está disponible en este equipo.", status_code=403, media_type="text/plain")

def _ctx_ajustes(con, **extra):
    from . import movil
    activo = movil.activado(con)
    ctx = {"activo": activo, "hay": bool(repo.empresas(con)), "ok": "", "error": "",
           "dispositivos": movil.listar(con) if activo else [],
           "direcciones": movil.direcciones() if activo else [],
           "puerto": movil.puerto() if activo else None,
           "huella": movil.huella() if activo else None,
           "bloqueo": movil.bloqueo_hasta(con) if activo else None,
           "en_marcha": movil.en_marcha() if activo else False,
           "codigo": None, "qr": None, "expira": None}
    ctx.update(extra)
    return ctx

@app.get("/ajustes", response_class=HTMLResponse)
def ajustes_ver(request: Request, ok: str = ""):
    if not _solo_este_equipo(request):
        return _rechazo_remoto()
    return tpl.TemplateResponse(request, "ajustes.html", _ctx_ajustes(db(), ok=ok))

@app.post("/ajustes", response_class=HTMLResponse)
async def ajustes_guardar(request: Request):
    if not _solo_este_equipo(request):
        return _rechazo_remoto()
    from . import movil
    f = await request.form()
    con = db()
    querer = f.get("permitir") == "1"
    try:
        if querer:
            movil.activar(con)
        else:
            movil.desactivar(con)
    except movil.ErrorMovil as ex:
        return tpl.TemplateResponse(request, "ajustes.html", _ctx_ajustes(con, error=str(ex)), status_code=400)
    return RedirectResponse("/ajustes?ok=" + ("activado" if querer else "desactivado"), status_code=303)

@app.post("/ajustes/emparejar", response_class=HTMLResponse)
async def ajustes_emparejar(request: Request):
    if not _solo_este_equipo(request):
        return _rechazo_remoto()
    from markupsafe import Markup
    from . import movil
    con = db()
    if not movil.activado(con):
        return tpl.TemplateResponse(request, "ajustes.html",
                                    _ctx_ajustes(con, error="El acceso desde el móvil está desactivado."), status_code=400)
    try:
        gen = movil.nuevo_codigo(con)
    except movil.ErrorMovil as ex:
        return tpl.TemplateResponse(request, "ajustes.html", _ctx_ajustes(con, error=str(ex)), status_code=400)
    dirs = movil.direcciones()
    huella = movil.huella()
    payload = movil.payload_json(movil.payload_qr(gen["codigo"], [d["ip"] for d in dirs], movil.puerto(), huella or ""))
    svg = movil.qr_svg(payload)
    return tpl.TemplateResponse(request, "ajustes.html", _ctx_ajustes(
        con, codigo=gen["codigo"], expira=gen["expira"].strftime("%H:%M"), qr=Markup(svg) if svg else None))

@app.post("/ajustes/revocar")
async def ajustes_revocar(request: Request):
    if not _solo_este_equipo(request):
        return _rechazo_remoto()
    from . import movil
    f = await request.form()
    try:
        did = int(f.get("id") or "")
    except ValueError:
        raise ErrorNegocio("Elija el dispositivo que quiere revocar.")
    con = db()
    movil.revocar(con, did)
    return RedirectResponse("/ajustes?ok=revocado", status_code=303)

@app.post("/ajustes/desbloquear")
async def ajustes_desbloquear(request: Request):
    if not _solo_este_equipo(request):
        return _rechazo_remoto()
    from . import movil
    movil.desbloquear(db())
    return RedirectResponse("/ajustes?ok=desbloqueado", status_code=303)

# ------------------------------------------------------------------------------------------------ 0.0.5: buscador
@app.get("/e/{eid}/buscar", response_class=HTMLResponse)
def buscar(request: Request, eid: int, q: str = ""):
    con = db(); e = _emp(con, eid)
    return tpl.TemplateResponse(request, "buscar.html", {"e": e, "r": repo.buscar(con, eid, q), "q": q})

@app.get("/salud")
def salud():
    return Response(f"ContFactu OK {VERSION}", media_type="text/plain")

@app.get("/acerca", response_class=HTMLResponse)
def acerca(request: Request):
    import platform
    from .ventana import modo_actual
    return tpl.TemplateResponse(request, "acerca.html", {"programa": os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else str(Path(__file__).resolve().parent.parent), "datos": str(db_path()), "python": platform.python_version(),
                                                         "modo": modo_actual(), "iconos": iconos.nombres()})

@app.get("/splash.png")
def splash_png():
    import io
    from herramientas.splash import generar
    import tempfile
    ruta = os.path.join(tempfile.gettempdir(), f"contfactu_splash_{VERSION}.png")
    if not os.path.exists(ruta):
        generar(ruta, lado=380, ver=VERSION)
    with open(ruta, "rb") as f:
        return Response(f.read(), media_type="image/png")

# La ventana propia (pywebview) registra aquí cómo traerse al frente; lo usa una segunda instancia.
MOSTRAR = {"fn": None}

@app.post("/_mostrar")
def mostrar_ventana(request: Request):
    if request.client and request.client.host not in ("127.0.0.1", "::1", "testclient"):
        return Response(status_code=403)
    if MOSTRAR["fn"]:
        MOSTRAR["fn"]()
        return Response("ok", media_type="text/plain")
    return Response("sin ventana", media_type="text/plain", status_code=409)
