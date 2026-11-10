"""API estable para la aplicación Android (ContFactu 0.2.0).

Solo existe como servidor propio, y solo cuando el usuario ha activado el acceso
desde el móvil. No está montada en el servidor de la ventana.

Alcance de esta versión: empresas (para elegir cuál), facturas (consultar, crear,
editar y PDF), clientes y búsqueda de clientes y facturas. No hay descarga de la
base, ni copias de seguridad, ni borrado, ni correo. Crear y editar pasa por
repo.guardar_documento: el IVA de cada línea es el que ya admite el programa
(cualquier tipo entre 0 y 100 con hasta dos decimales).

Los importes van en texto con punto decimal, nunca en coma flotante.
"""
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from . import movil
from .repo import ErrorNegocio

API_VERSION = 1
# Lista cerrada. Un endpoint nuevo tiene que añadirse aquí y en docs/api-movil.md.
RUTAS = {
    ("GET", "/api/v1/salud"),
    ("POST", "/api/v1/emparejar/confirmar"),
    ("POST", "/api/v1/emparejar"),
    ("GET", "/api/v1/empresas"),
    ("GET", "/api/v1/empresas/{eid}/facturas"),
    ("GET", "/api/v1/empresas/{eid}/facturas/{did}"),
    ("POST", "/api/v1/empresas/{eid}/facturas"),
    ("PUT", "/api/v1/empresas/{eid}/facturas/{did}"),
    ("GET", "/api/v1/empresas/{eid}/facturas/{did}/pdf"),
    ("GET", "/api/v1/empresas/{eid}/clientes"),
    ("GET", "/api/v1/empresas/{eid}/clientes/{cid}"),
    ("GET", "/api/v1/empresas/{eid}/buscar"),
}

aplicacion = FastAPI(title="ContFactu móvil", version=str(API_VERSION), docs_url=None, redoc_url=None, openapi_url=None)

def _conectar():
    from . import db
    return db.connect()

def _cuerpo_error(detail, status):
    if isinstance(detail, dict):
        cuerpo = {"error": detail.get("error") or "Error"}
        if "reintentar_en" in detail:
            cuerpo["reintentar_en"] = detail["reintentar_en"]
        return JSONResponse(cuerpo, status_code=status)
    return JSONResponse({"error": str(detail)}, status_code=status)

@aplicacion.exception_handler(HTTPException)
async def _http(request, exc):
    return _cuerpo_error(exc.detail, exc.status_code)

@aplicacion.exception_handler(RequestValidationError)
async def _validacion(request, exc):
    return JSONResponse({"error": "La petición no es válida."}, status_code=400)

def _respuesta_negocio(exc):
    cuerpo = {"error": str(exc)}
    if getattr(exc, "campo", None):
        cuerpo["campo"] = exc.campo
    if getattr(exc, "indice", None) is not None:
        cuerpo["indice"] = exc.indice
    return JSONResponse(cuerpo, status_code=400)

@aplicacion.exception_handler(ErrorNegocio)
async def _negocio(request, exc):
    return _respuesta_negocio(exc)

@aplicacion.exception_handler(Exception)
async def _inesperado(request, exc):
    if isinstance(exc, HTTPException):
        return _cuerpo_error(exc.detail, exc.status_code)
    if isinstance(exc, ErrorNegocio):
        return _respuesta_negocio(exc)
    if isinstance(exc, RequestValidationError):
        return JSONResponse({"error": "La petición no es válida."}, status_code=400)
    return JSONResponse({"error": "No se ha podido completar la operación."}, status_code=500)

@aplicacion.middleware("http")
async def _solo_si_activo(request, call_next):
    con = _conectar()
    try:
        on = movil.activado(con)
    finally:
        con.close()
    if not on:
        resp = JSONResponse({"error": "No disponible."}, status_code=404)
    else:
        resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

def exigir(request: Request):
    """Comprueba el token y cierra esa conexión. La ruta abre otra: SQLite no admite usar la misma en dos hilos,
    y FastAPI puede ejecutar la dependencia y la ruta en hilos distintos. El token no se acepta en la query."""
    cab = request.headers.get("authorization") or ""
    token = cab[7:].strip() if cab[:7].lower() == "bearer " else ""
    con = _conectar()
    try:
        disp = movil.dispositivo_por_token(con, token)
        if not disp:
            raise HTTPException(401, "Acceso no autorizado.")
        movil.tocar(con, disp["id"])
    finally:
        con.close()

async def _json(request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "El cuerpo debe ser JSON.")
    if not isinstance(body, dict):
        raise HTTPException(400, "El cuerpo debe ser un objeto JSON.")
    return body

def _num(v, defecto="0"):
    from .calc import dec
    if v is None:
        return defecto
    s = str(v).strip().replace(" ", "")
    if not s:
        return defecto
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        dec(s)
    except Exception:
        raise ErrorNegocio(f"Número no válido: «{v}».")
    return s

def _bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "si", "sí"):
        return True
    return False

def _lineas(raw):
    if not isinstance(raw, list) or not raw:
        raise ErrorNegocio("El documento no tiene líneas.")
    res = []
    for i, l in enumerate(raw, 1):
        if not isinstance(l, dict):
            raise ErrorNegocio(f"La línea {i} no es válida.")
        concepto = (l.get("concepto") or "").strip()
        if l.get("comentario") is True:
            res.append({"codigo": l.get("codigo") or "", "concepto": concepto, "comentario": 1,
                        "cantidad": "", "precio": "", "descuento": "", "iva": ""})
            continue
        if l.get("precio") in (None, ""):
            raise ErrorNegocio(f"Línea {i}: falta el precio.")
        res.append({"codigo": l.get("codigo") or "", "concepto": concepto, "comentario": 0,
                    "cantidad": _num(l.get("cantidad"), "1"), "precio": _num(l.get("precio")),
                    "descuento": _num(l.get("descuento")),
                    "iva": "" if l.get("iva") in (None, "") else str(l.get("iva")).strip()})
    return res

def _datos(con, eid, body, edicion):
    if not isinstance(body, dict):
        raise ErrorNegocio("El cuerpo debe ser un objeto JSON.")
    datos = {}
    for k in ("fecha", "nombre_f", "direccion_f", "ciudad_f", "nif", "forma_pago", "cliente_codigo", "domiciliacion", "ccc"):
        if k in body and body[k] is not None:
            datos[k] = str(body[k]).strip()
    if body.get("cliente_id") not in (None, ""):
        try:
            cid = int(body["cliente_id"])
        except (TypeError, ValueError):
            raise ErrorNegocio("El cliente no es válido.")
        c = con.execute("SELECT * FROM clientes WHERE id=? AND empresa_id=?", (cid, eid)).fetchone()
        if not c:
            raise ErrorNegocio("El cliente no existe en esta empresa.")
        c = dict(c)
        relleno = {"cliente_codigo": c.get("codigo"), "nombre_f": c.get("nombre_f") or c.get("nombre"),
                   "direccion_f": c.get("direccion_f") or c.get("direccion"),
                   "ciudad_f": c.get("ciudad_f") or c.get("ciudad"), "nif": c.get("nif"), "forma_pago": c.get("forma_pago")}
        for k, v in relleno.items():
            if not datos.get(k) and v:
                datos[k] = v
        if "descuento" not in body and c.get("descuento") not in (None, ""):
            body = dict(body, descuento=c.get("descuento"))
    if not (datos.get("nombre_f") or "").strip():
        raise ErrorNegocio("Falta el nombre del cliente.")
    datos["descuento"] = _num(body.get("descuento"))
    datos["retencion"] = _num(body.get("retencion"))
    datos["re"] = _bool(body.get("re"))
    datos["exento"] = _bool(body.get("exento"))
    datos["iva_incluido"] = _bool(body.get("iva_incluido"))
    if not edicion and body.get("serie") is not None:
        datos["serie"] = str(body.get("serie") or "").strip()[:3]
    return datos, _lineas(body.get("lineas"))

def _empresa_o_404(con, eid):
    from . import repo
    e = repo.empresa(con, eid)
    if not e:
        raise HTTPException(404, "No encontrado.")
    return e

def _factura_o_404(con, eid, did):
    from . import repo
    d, ls, ps = repo.documento(con, did)
    if not d or d["empresa_id"] != eid or d["tipo"] != "F":
        raise HTTPException(404, "No encontrado.")
    return d, ls, ps

def _desglose(d):
    from .calc import tramos_iva
    res = []
    for b, iva, re in tramos_iva(d):
        if b == 0:
            continue
        res.append({"base": format(b, "f"), "iva": format(iva, "f"), "re": format(re, "f")})
    return res

def _resumen(d):
    from . import repo
    return {"id": d["id"], "numero": d.get("numero"), "serie": d.get("serie") or "",
            "numero_visible": repo.num_visible(d), "fecha": d.get("fecha"), "nombre_f": d.get("nombre_f"),
            "nif": d.get("nif"), "total": d.get("total"), "pendiente": d.get("pendiente"),
            "estado": repo.estado_cobro(d)}

def _linea_json(l):
    return {"orden": l.get("orden"), "codigo": l.get("codigo") or "", "concepto": l.get("concepto") or "",
            "cantidad": l.get("cantidad") or "", "precio": l.get("precio") or "",
            "descuento": l.get("descuento") or "0", "iva": l.get("iva") or "",
            "comentario": bool(l.get("comentario"))}

def _detalle(d, ls):
    from . import repo
    x = _resumen(d)
    x.update({"fecha_operacion": d.get("fecha_operacion"), "direccion_f": d.get("direccion_f"),
              "ciudad_f": d.get("ciudad_f"), "cliente_codigo": d.get("cliente_codigo"),
              "forma_pago": d.get("forma_pago"), "descuento": d.get("descuento") or "0",
              "retencion": d.get("retencion") or "0", "exento": bool(d.get("exento")),
              "iva_incluido": bool(d.get("iva_incluido")), "re": repo._con_re(d),
              "desglose": _desglose(d), "lineas": [_linea_json(l) for l in ls]})
    return x

def _empresa_json(e):
    from . import altas
    return {"id": e["id"], "codigo": e.get("codigo"), "nombre": e.get("nombre"), "nif": e.get("nif"),
            "ivas": altas.ivas_de(e), "re_tasas": altas.tasas_re_de(e), "n_facturas": e.get("n_facturas") or 0}

def _limite(v, defecto=200, maximo=500):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return defecto
    return max(1, min(n, maximo))

CAMPOS_CLIENTE = ("id", "codigo", "nombre", "nombre_f", "nif", "direccion", "direccion_f", "ciudad", "ciudad_f",
                  "telefono", "movil", "email", "contacto", "forma_pago", "dias_pago", "descuento", "recargo",
                  "retiene", "ccc", "bic", "domiciliacion")

def _cliente_json(c):
    return {k: c[k] if k in c.keys() else None for k in CAMPOS_CLIENTE}

@aplicacion.get("/api/v1/salud")
def salud():
    from . import __version__
    return {"nombre": "ContFactu", "api": API_VERSION, "version": __version__}

@aplicacion.post("/api/v1/emparejar/confirmar")
async def emparejar_confirmar(request: Request):
    """Paso manual: el móvil demuestra que vio el certificado de este PC sin enviar todavía el código."""
    body = await _json(request)
    con = _conectar()
    try:
        try:
            return {"confirmacion": movil.confirmar_emparejamiento(con, body.get("prueba"))}
        except movil.CodigoRechazado:
            raise HTTPException(401, "El código no es válido o ha caducado.")
        except movil.EmparejamientoBloqueado as ex:
            raise HTTPException(429, {"error": "Demasiados intentos. El emparejamiento está bloqueado un momento.",
                                       "reintentar_en": ex.segundos})
        except movil.ErrorMovil as ex:
            raise HTTPException(400, str(ex))
    finally:
        con.close()

@aplicacion.post("/api/v1/emparejar")
async def emparejar(request: Request):
    body = await _json(request)
    con = _conectar()
    try:
        try:
            return movil.emparejar(con, body.get("codigo"), body.get("nombre"))
        except movil.CodigoRechazado:
            raise HTTPException(401, "El código no es válido o ha caducado.")
        except movil.EmparejamientoBloqueado as ex:
            raise HTTPException(429, {"error": "Demasiados intentos. El emparejamiento está bloqueado un momento.",
                                       "reintentar_en": ex.segundos})
        except movil.ErrorMovil as ex:
            raise HTTPException(400, str(ex))
    finally:
        con.close()

@aplicacion.get("/api/v1/empresas")
def empresas(_auth=Depends(exigir)):
    from . import repo
    con = _conectar()
    try:
        return {"empresas": [_empresa_json(e) for e in repo.empresas(con)]}
    finally:
        con.close()

@aplicacion.get("/api/v1/empresas/{eid}/facturas")
def facturas(eid: int, anio: str = "", q: str = "", limite: int = 200, _auth=Depends(exigir)):
    con = _conectar()
    try:
        return _facturas(con, eid, anio, q, limite)
    finally:
        con.close()

def _facturas(con, eid, anio, q, limite):
    _empresa_o_404(con, eid)
    anios = [r[0] for r in con.execute(
        "SELECT DISTINCT substr(fecha,1,4) FROM documentos WHERE empresa_id=? AND tipo='F' AND fecha IS NOT NULL ORDER BY 1 DESC",
        (eid,))]
    if not anio and anios:
        anio = anios[0]
    sql = "SELECT * FROM documentos WHERE empresa_id=? AND tipo='F'"
    args = [eid]
    if anio and anio != "todos":
        sql += " AND substr(fecha,1,4)=?"
        args.append(anio)
    if q:
        sql += " AND (nombre_f LIKE ? OR numero LIKE ? OR nif LIKE ? OR (serie || numero) LIKE ?)"
        args += [f"%{q}%"] * 4
    sql += " ORDER BY fecha DESC, serie DESC, numero DESC LIMIT ?"
    args.append(_limite(limite))
    docs = [_resumen(dict(r)) for r in con.execute(sql, args)]
    return {"anio": anio if anio != "todos" else "todos", "anios": anios, "facturas": docs}

@aplicacion.get("/api/v1/empresas/{eid}/facturas/{did}")
def factura(eid: int, did: int, _auth=Depends(exigir)):
    con = _conectar()
    try:
        _empresa_o_404(con, eid)
        d, ls, _ps = _factura_o_404(con, eid, did)
        return _detalle(d, ls)
    finally:
        con.close()

@aplicacion.post("/api/v1/empresas/{eid}/facturas", status_code=201)
async def crear_factura(eid: int, request: Request, _auth=Depends(exigir)):
    from . import repo
    body = await _json(request)
    con = _conectar()
    try:
        _empresa_o_404(con, eid)
        datos, lineas = _datos(con, eid, body, edicion=False)
        with con:
            did = repo.guardar_documento(con, eid, "F", datos, lineas)
        d, ls, _ps = repo.documento(con, did)
        return JSONResponse(_detalle(d, ls), status_code=201)
    finally:
        con.close()

@aplicacion.put("/api/v1/empresas/{eid}/facturas/{did}")
async def editar_factura(eid: int, did: int, request: Request, _auth=Depends(exigir)):
    from . import repo
    body = await _json(request)
    con = _conectar()
    try:
        _empresa_o_404(con, eid)
        _factura_o_404(con, eid, did)
        datos, lineas = _datos(con, eid, body, edicion=True)
        with con:
            repo.guardar_documento(con, eid, "F", datos, lineas, did=did)
        d, ls, _ps = repo.documento(con, did)
        return _detalle(d, ls)
    finally:
        con.close()

@aplicacion.get("/api/v1/empresas/{eid}/facturas/{did}/pdf")
def pdf_factura(eid: int, did: int, _auth=Depends(exigir)):
    con = _conectar()
    try:
        _empresa_o_404(con, eid)
        d, ls, ps = _factura_o_404(con, eid, did)
        from .main import _pdf_documento
        data, nombre = _pdf_documento(con, d, ls, ps)
        return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nombre}"'})
    finally:
        con.close()

@aplicacion.get("/api/v1/empresas/{eid}/clientes")
def clientes(eid: int, q: str = "", limite: int = 200, _auth=Depends(exigir)):
    con = _conectar()
    try:
        return _clientes(con, eid, q, limite)
    finally:
        con.close()

def _clientes(con, eid, q, limite):
    _empresa_o_404(con, eid)
    like = f"%{q}%"
    cols = ", ".join(CAMPOS_CLIENTE)
    rows = con.execute(f"""SELECT {cols} FROM clientes WHERE empresa_id=? AND (nombre LIKE ? OR nombre_f LIKE ?
        OR nif LIKE ? OR codigo LIKE ? OR ciudad LIKE ?) ORDER BY nombre LIMIT ?""",
                       (eid, like, like, like, like, like, _limite(limite)))
    return {"clientes": [_cliente_json(r) for r in rows]}

@aplicacion.get("/api/v1/empresas/{eid}/clientes/{cid}")
def cliente(eid: int, cid: int, _auth=Depends(exigir)):
    con = _conectar()
    try:
        _empresa_o_404(con, eid)
        cols = ", ".join(CAMPOS_CLIENTE)
        r = con.execute(f"SELECT {cols} FROM clientes WHERE id=? AND empresa_id=?", (cid, eid)).fetchone()
        if not r:
            raise HTTPException(404, "No encontrado.")
        return _cliente_json(r)
    finally:
        con.close()

@aplicacion.get("/api/v1/empresas/{eid}/buscar")
def buscar(eid: int, q: str = "", _auth=Depends(exigir)):
    from . import repo
    con = _conectar()
    try:
        return _buscar(con, eid, q, repo)
    finally:
        con.close()

def _buscar(con, eid, q, repo):
    _empresa_o_404(con, eid)
    r = repo.buscar(con, eid, q)
    clientes_r = [{"id": c["id"], "codigo": c.get("codigo"), "nombre": c.get("nombre"), "nombre_f": c.get("nombre_f"),
                   "nif": c.get("nif"), "ciudad": c.get("ciudad")} for c in r["clientes"]]
    facturas_r = []
    for d in r["documentos"]:
        if d.get("tipo") != "F":
            continue
        facturas_r.append({"id": d["id"], "numero_visible": d.get("visible"), "fecha": d.get("fecha"),
                           "nombre_f": d.get("nombre_f"), "nif": d.get("nif"), "total": d.get("total"),
                           "pendiente": d.get("pendiente"), "estado": d.get("estado")})
    return {"q": r["q"], "clientes": clientes_r, "facturas": facturas_r, "total": len(clientes_r) + len(facturas_r)}
