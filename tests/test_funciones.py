"""Tests de las funciones de la fase 2: editar/borrar, rectificativas, cobros y recibos, pasar a factura,
libros de IVA y empaquetado. Usan una empresa ficticia en una base temporal (sin datos reales)."""
import io, os, csv, importlib, shutil
from decimal import Decimal as D
from pathlib import Path
import pytest

# Copia real de FactuCont 5 (opcional): CONTFACTU_FC5=carpeta FC5. Sin ella, esas pruebas se saltan.
FC5 = Path(os.environ.get("CONTFACTU_FC5") or "/no-existe/FC5")
RAIZ = Path(__file__).resolve().parent.parent

@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTFACTU_DB", str(tmp_path / "t.db"))
    import app.db
    importlib.reload(app.db)
    c = app.db.connect()
    with c:
        c.execute("INSERT INTO empresas(id,codigo,nombre,nif,direccion,ciudad) VALUES(1,'99999','Empresa de Prueba SL','B00000000','C/ Falsa 1','Madrid')")
    return c

def L(concepto, cant, precio, iva="21", dto="0"):
    return {"concepto": concepto, "cantidad": str(cant), "precio": str(precio), "iva": str(iva), "descuento": dto}

def nueva(con, tipo="F", fecha="2026-03-10", lineas=None, **kw):
    from app import repo
    datos = {"fecha": fecha, "nombre_f": kw.pop("cliente", "Cliente Uno"), "nif": kw.pop("nif", "12345678Z"), **kw}
    with con:
        return repo.guardar_documento(con, 1, tipo, datos, lineas or [L("Servicio", 1, 100)])

def d_(con, did):
    from app import repo
    return repo.doc(con, did)

# ------------------------------------------------------------------------------------- 1. editar y borrar
def test_crear_todos_los_tipos_y_numeracion(con):
    for t in ("F", "P", "A", "G", "M"):
        a, b = nueva(con, t), nueva(con, t)
        assert d_(con, a)["numero"] == "260001" and d_(con, b)["numero"] == "260002"
    assert d_(con, a)["total"] == "121.00"

def test_editar_recalcula_totales_y_vencimientos(con):
    from app import repo
    did = nueva(con)
    with con:
        repo.guardar_documento(con, 1, "F", {"fecha": "2026-03-10", "nombre_f": "Cliente Uno", "re": True},
                               [L("A", 2, 50), L("B", 1, 100, iva="10"), {"concepto": "comentario"}], did)
    d, ls, ps = repo.documento(con, did)
    # 100 al 21 % + RE 5,2 % y 100 al 10 % + RE 1,4 %
    assert d["total"] == str(D("100") + D("21") + D("5.20") + D("100") + D("10") + D("1.40"))
    assert d["pendiente"] == d["total"] and len(ls) == 3 and ls[2]["comentario"] == 1
    vto = [p for p in ps if p["tipo"] == ""]
    assert len(vto) == 1 and vto[0]["importe"] == d["total"]

def test_editar_no_permite_fecha_fuera_de_orden(con):
    from app import repo
    a = nueva(con, fecha="2026-03-01"); b = nueva(con, fecha="2026-03-05"); c = nueva(con, fecha="2026-03-09")
    with pytest.raises(repo.ErrorNegocio, match="anterior"):
        with con: repo.guardar_documento(con, 1, "F", {"fecha": "2026-02-01", "nombre_f": "X"}, [L("a", 1, 1)], b)
    with pytest.raises(repo.ErrorNegocio, match="posterior"):
        with con: repo.guardar_documento(con, 1, "F", {"fecha": "2026-03-20", "nombre_f": "X"}, [L("a", 1, 1)], b)
    with pytest.raises(repo.ErrorNegocio, match="anterior"):  # alta nueva con fecha anterior a la última
        nueva(con, fecha="2026-03-02")

def test_editar_con_cobros_no_deja_total_menor(con):
    from app import repo
    did = nueva(con)
    with con: repo.registrar_cobro(con, did, "100", "2026-03-11")
    with pytest.raises(repo.ErrorNegocio, match="cobrados"):
        with con: repo.guardar_documento(con, 1, "F", {"fecha": "2026-03-10", "nombre_f": "X"}, [L("a", 1, 10)], did)
    with con: repo.guardar_documento(con, 1, "F", {"fecha": "2026-03-10", "nombre_f": "X"}, [L("a", 1, 200)], did)
    assert d_(con, did)["pendiente"] == "142.00"  # 242 - 100 cobrados

def test_editar_importado_lo_marca_editado(con):
    from app import repo
    did = nueva(con)
    con.execute("UPDATE documentos SET origen='factucont' WHERE id=?", (did,))
    with con: repo.guardar_documento(con, 1, "F", {"fecha": "2026-03-10", "nombre_f": "X"}, [L("a", 1, 10)], did)
    assert d_(con, did)["origen"] == "editado"

def test_borrar_ultima_ok_y_no_ultima_exige_forzar(con):
    from app import repo
    a, b = nueva(con), nueva(con)
    info = repo.info_borrado(con, a)
    assert info["rompe_numeracion"] and "rectificativa" in info["avisos"][0].lower()
    with pytest.raises(repo.AvisoNumeracion):
        with con: repo.borrar_documento(con, a)
    with con: repo.borrar_documento(con, b)          # la última: sin aviso
    assert not repo.info_borrado(con, a)["rompe_numeracion"]
    c = nueva(con)
    with con: repo.borrar_documento(con, a, forzar=True)
    assert con.execute("SELECT COUNT(*) FROM documentos").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM lineas WHERE documento_id=?", (a,)).fetchone()[0] == 0

def test_borrar_otros_tipos_sin_aviso(con):
    from app import repo
    p1, p2 = nueva(con, "P"), nueva(con, "P")
    with con: repo.borrar_documento(con, p1)
    assert d_(con, p2)

# ------------------------------------------------------------------------------------- 2. rectificativas
def test_rectificativa_por_diferencias(con):
    from app import repo
    f = nueva(con, lineas=[L("Producto", 2, 50), L("Libro", 1, 20, iva="4")])
    with con: r = repo.crear_rectificativa(con, f, "I", "Devolución de una unidad", "R4", "2026-03-15",
                                           [L("Producto devuelto", -1, 50)])
    d = d_(con, r)
    assert d["serie"] == "R" and d["numero"] == "260001" and d["total"] == "-60.50"
    assert d["rect_original_id"] == f and d["rect_tipo"] == "I" and d["vf_tipo_factura"] == "R4"
    assert d["rect_base_original"] == "120.00"
    # el abono se compensa con lo que debía el cliente de la original
    assert d_(con, f)["pendiente"] == str(D("141.80") - D("60.50")) and d["pendiente"] == "0.00"
    # la numeración R es independiente de la normal
    assert d_(con, nueva(con, fecha="2026-03-16"))["numero"] == "260002"

def test_rectificativa_por_diferencias_lineas_por_defecto_negativas(con):
    from app import repo
    f = nueva(con)
    with con: r = repo.crear_rectificativa(con, f, "I", "Anulación", fecha="2026-03-12")
    assert d_(con, r)["total"] == "-121.00" and d_(con, f)["pendiente"] == "0.00"

def test_rectificativa_por_sustitucion(con):
    from app import repo
    f = nueva(con)
    with con: repo.registrar_cobro(con, f, "21", "2026-03-11")
    with con: r = repo.crear_rectificativa(con, f, "S", "Precio erróneo", "R1", "2026-03-12", [L("Servicio", 1, 80)])
    d = d_(con, r)
    assert d["total"] == "96.80" and d["pendiente"] == "75.80"  # lo cobrado (21) se traslada
    assert d_(con, f)["pendiente"] == "0" and d["rect_cuota_original"] == "21.00"
    with con: repo.borrar_documento(con, r)  # al borrarla, la original recupera su pendiente
    assert d_(con, f)["pendiente"] == "100.00"

def test_rectificativa_validaciones_y_bloqueo_borrado_original(con):
    from app import repo
    f = nueva(con); p = nueva(con, "P")
    with pytest.raises(repo.ErrorNegocio): repo.crear_rectificativa(con, p, "I", "x")
    with pytest.raises(repo.ErrorNegocio, match="motivo"): repo.crear_rectificativa(con, f, "I", " ")
    with pytest.raises(repo.ErrorNegocio, match="anterior"): repo.crear_rectificativa(con, f, "I", "x", fecha="2026-01-01")
    with con: repo.crear_rectificativa(con, f, "I", "x", fecha="2026-03-20")
    with pytest.raises(repo.ErrorNegocio, match="rectificativas"):
        repo.borrar_documento(con, f, forzar=True)

@pytest.mark.skipif(not FC5.exists(), reason="sin diseños de FactuCont")
def test_pdf_rectificativa_titulo_y_referencia(con):
    from app import repo
    from app.fmt_pdf import render_pdf
    fmt = (FC5 / "00008" / "factura.fmt").read_text(encoding="cp1252")
    f = nueva(con)
    with con: r = repo.crear_rectificativa(con, f, "I", "Devolución total", fecha="2026-03-20")
    d, ls, ps = repo.documento(con, r)
    ref = repo.lineas_referencia_rectificativa(con, d)
    assert "260001" in ref[0] and "10/03/2026" in ref[0] and "Devolución total" in ref[1]
    pdf = render_pdf(fmt, repo.empresa(con, 1), d, ls, ps, lineas_previas=ref)
    txt = _texto_pdf(pdf)
    assert "FACTURA RECTIFICATIVA" in txt and "Rectifica a la factura" in txt and "R260001" in txt

def _texto_pdf(data):
    import shutil, subprocess, tempfile
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext (poppler) no disponible para leer el PDF")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as t:
        t.write(data); t.flush()
        return subprocess.run(["pdftotext", "-layout", t.name, "-"], capture_output=True, text=True).stdout

# ------------------------------------------------------------------------------------- 3. cobros y recibos
def test_cobro_parcial_total_y_anulacion(con):
    from app import repo
    f = nueva(con)
    with con: repo.registrar_cobro(con, f, "21", "2026-03-11", "Efectivo")
    assert repo.estado_cobro(d_(con, f)) == "parcial" and d_(con, f)["pendiente"] == "100.00"
    with pytest.raises(repo.ErrorNegocio, match="superar"):
        repo.registrar_cobro(con, f, "100.01")
    with con: repo.registrar_cobro(con, f, "100")
    assert repo.estado_cobro(d_(con, f)) == "cobrado"
    assert f not in [p["id"] for p in repo.pendientes(con, 1)]
    cid = repo.cobros(con, f)[0]["id"]
    with con: repo.anular_cobro(con, cid)
    assert d_(con, f)["pendiente"] == "21.00"
    with pytest.raises(repo.ErrorNegocio, match="cero"):
        repo.registrar_cobro(con, f, "0")

def test_cobro_reparte_entre_vencimientos(con):
    from app import repo
    f = nueva(con)  # 121 €
    con.execute("DELETE FROM plazos WHERE documento_id=? AND tipo=''", (f,))
    for fecha, imp in (("2026-04-10", "60.50"), ("2026-05-10", "60.50")):
        con.execute("INSERT INTO plazos(documento_id,empresa_id,referencia,tipo,fecha,concepto,importe) VALUES(?,1,'x','',?,?,?)", (f, fecha, "Plazo", imp))
    with con: repo.registrar_cobro(con, f, "80")
    ps = [p for p in repo.documento(con, f)[2] if p["tipo"] == ""]
    assert [p["cobrado"] for p in ps] == ["60.50", "19.50"]
    assert len(repo.cobros(con, f)) == 2
    pend = repo.pendientes(con, 1, hasta="2026-06-01")
    assert pend[0]["vencido"] and pend[0]["vencimiento"] == "2026-05-10"

def test_cobro_importado_sin_vencimientos(con):
    """Documentos de FactuCont cuyo pendiente no cuadra con sus vencimientos: el cobro se registra igual."""
    from app import repo
    f = nueva(con)
    con.execute("DELETE FROM plazos WHERE documento_id=?", (f,))
    with con: repo.registrar_cobro(con, f, "121")
    assert d_(con, f)["pendiente"] == "0.00" and repo.cobros(con, f)[0]["plazo_id"] is None

def test_pendientes_incluye_albaranes_no_facturados(con):
    from app import repo
    a = nueva(con, "A"); p = nueva(con, "P")
    ids = [x["id"] for x in repo.pendientes(con, 1)]
    assert a in ids and p not in ids
    with con: repo.facturar(con, [a], "2026-03-20")
    assert a not in [x["id"] for x in repo.pendientes(con, 1)]

def test_importe_en_letra():
    from app.letras import importe_a_letras as f
    assert f("2383.70") == "DOS MIL TRESCIENTOS OCHENTA Y TRES EUROS CON SETENTA CÉNTIMOS"
    assert f(1) == "UN EURO" and f(21) == "VEINTIÚN EUROS" and f(100) == "CIEN EUROS" and f(101) == "CIENTO UN EUROS"
    assert f("1000000") == "UN MILLÓN EUROS" and f("0.01") == "CERO EUROS CON UN CÉNTIMO"
    assert f("1515.15") == "MIL QUINIENTOS QUINCE EUROS CON QUINCE CÉNTIMOS"

def test_ccc():
    from app.fmt_pdf import ccc_partes
    assert ccc_partes("ES91 2100 0418 4502 0005 1332") == ("2100", "0418", "45", "0200051332")

@pytest.mark.skipif(not FC5.exists(), reason="sin diseños de FactuCont")
def test_recibo_pdf_con_diseno_factucont(con):
    from app import repo
    from app.fmt_pdf import render_recibos
    fmt = (FC5 / "00008" / "Recibo.fmt").read_text(encoding="cp1252")
    f = nueva(con, lineas=[L("Servicio", 1, "1970")])  # 2383,70
    rs = repo.recibos_documento(con, f)
    txt = _texto_pdf(render_recibos(fmt, repo.empresa(con, 1), d_(con, f), rs))
    assert "260001/1" in txt and "2.383,70" in txt and "DOS MIL TRESCIENTOS" in txt and "Cliente Uno" in txt

def test_recibo_pdf_sin_diseno(con):
    from app import repo
    from app.fmt_pdf import render_recibos
    f = nueva(con)
    txt = _texto_pdf(render_recibos(None, repo.empresa(con, 1), d_(con, f), repo.recibos_documento(con, f)))
    assert "RECIBO" in txt and "CIENTO VEINTIÚN EUROS" in txt

# ------------------------------------------------------------------------------------- 4. pasar a factura
def test_varios_albaranes_a_una_factura(con):
    from app import repo
    a1 = nueva(con, "A", "2026-03-01", [L("Tornillos", 100, "0.10")])
    a2 = nueva(con, "A", "2026-03-05", [L("Tuercas", 50, "0.20"), L("Libro", 1, 10, iva="4")])
    with con: f = repo.facturar(con, [a2, a1], "2026-03-31")
    d, ls, _ = repo.documento(con, f)
    assert d["tipo"] == "F" and d["total"] == str(D("20") + D("4.20") + D("10.40"))
    assert ls[0]["comentario"] and "Albarán nº 260001 de fecha 01/03/2026" == ls[0]["concepto"]
    assert [l["concepto"] for l in ls if not l["comentario"]] == ["Tornillos", "Tuercas", "Libro"]
    for a in (a1, a2):
        assert d_(con, a)["facturado"] == 1 and d_(con, a)["facturado_en_id"] == f
    with pytest.raises(repo.ErrorNegocio, match="facturados"):
        repo.facturar(con, [a1])
    with con: repo.borrar_documento(con, f)   # borrar la factura libera los albaranes
    assert d_(con, a1)["facturado"] == 0

def test_presupuesto_a_factura(con):
    from app import repo
    p = nueva(con, "P", lineas=[L("Reforma", 1, 1000)], retencion="15")
    with con: f = repo.facturar(con, [p], "2026-04-01")
    assert d_(con, f)["total"] == "1060.00" and d_(con, p)["facturado"] == 1

def test_facturar_validaciones(con):
    from app import repo
    a1 = nueva(con, "A"); a2 = nueva(con, "A", cliente="Otro", nif="X1234567L"); p = nueva(con, "P"); f = nueva(con, "F")
    with pytest.raises(repo.ErrorNegocio, match="mismo cliente"): repo.facturar(con, [a1, a2])
    with pytest.raises(repo.ErrorNegocio, match="mismo tipo"): repo.facturar(con, [a1, p])
    with pytest.raises(repo.ErrorNegocio): repo.facturar(con, [f])
    with pytest.raises(repo.ErrorNegocio): repo.facturar(con, [])

# ------------------------------------------------------------------------------------- 5. libros de IVA
def _datos_libro(con):
    from app import repo
    nueva(con, "F", "2026-01-15", [L("a", 1, 100), L("b", 1, 100, iva="10")], re=True)   # 1T
    nueva(con, "F", "2026-02-15", [L("c", 1, 1000)], retencion="15")                      # 1T
    nueva(con, "F", "2026-04-15", [L("d", 1, 50)])                                         # 2T
    nueva(con, "G", "2026-03-01", [L("Gasolina", 1, 50)], cliente="Gasolinera", num_factura_proveedor="T-77")
    nueva(con, "P", "2026-01-20", [L("no cuenta", 1, 999)])

def test_libro_emitidas_y_recibidas_por_trimestre(con):
    from app import repo
    _datos_libro(con)
    em = repo.libro(con, 1, "emitidas", "2026", "1")
    assert len({f["documento_id"] for f in em}) == 2 and len(em) == 3   # una fila por tipo de IVA
    r = repo.resumen_libro(em)
    assert r["base"] == D("1200") and r["cuota_iva"] == D("241") and r["cuota_re"] == D("6.60") and r["retencion"] == D("150")
    assert r["total"] == D("1200") + D("241") + D("6.60") - D("150")
    assert len(repo.libro(con, 1, "emitidas", "2026")) == 4
    rc = repo.libro(con, 1, "recibidas", "2026", "1")
    assert rc[0]["num_proveedor"] == "T-77" and rc[0]["cuota_iva"] == D("10.50")

def test_resumen_303(con):
    from app import repo
    _datos_libro(con)
    s = repo.resumen_303(con, 1, "2026", "1")
    c = {x["iva"]: x for x in s["devengado"]}
    assert c[D(21)]["casillas"] == ("07", "08", "09") and c[D(21)]["base"] == D("1100") and c[D(21)]["cuota"] == D("231")
    assert c[D(10)]["cuota"] == D("10") and sum(x["cuota"] for x in s["re"]) == D("6.60")
    assert s["c27"] == D("247.60") and s["c29"] == D("10.50") and s["c46"] == D("237.10")
    assert s["ret_emitidas"] == D("150")

def test_rectificativa_resta_en_libro(con):
    from app import repo
    f = nueva(con, "F", "2026-01-15")
    with con: repo.crear_rectificativa(con, f, "I", "anulación", fecha="2026-02-01")
    r = repo.resumen_libro(repo.libro(con, 1, "emitidas", "2026", "1"))
    assert r["base"] == 0 and r["cuota_iva"] == 0
    filas = repo.libro(con, 1, "emitidas", "2026", "1")
    assert filas[1]["tipo_factura"] == "R4" and filas[1]["rectifica"] == "260001"

def test_exportar_csv_y_xlsx(con):
    from app import repo
    from openpyxl import load_workbook
    _datos_libro(con)
    data = repo.libro_csv(repo.libro(con, 1, "emitidas", "2026", "1"), "emitidas")
    assert data.startswith(b"\xef\xbb\xbf")
    filas = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    assert filas[0][0] == "Fecha expedición" and filas[1][0] == "15/01/2026" and "100,00" in filas[1]
    wb = load_workbook(io.BytesIO(repo.libros_xlsx(con, 1, "2026", "1")))
    assert wb.sheetnames == ["Emitidas", "Recibidas", "Resumen por tipo", "Resumen 303"]
    ws = wb["Emitidas"]
    cab = [c.value for c in ws[2]]
    assert cab[:4] == ["Ejercicio", "Periodo", "Tipo de factura", "Fecha expedición"]
    assert ws.cell(3, cab.index("Base imponible") + 1).value == 100
    assert ws.cell(3, cab.index("Fecha expedición") + 1).number_format == "DD/MM/YYYY"
    assert any(r[0].value == "46" for r in wb["Resumen 303"].iter_rows())

# ------------------------------------------------------------------------------------- interfaz web
@pytest.fixture()
def cliente_web(con):
    import app.main
    importlib.reload(app.main)
    from fastapi.testclient import TestClient
    return TestClient(app.main.app)

def test_web_flujo_completo(con, cliente_web):
    c = cliente_web
    form = {"fecha": "2026-03-10", "nombre_f": "Cliente Web", "nif": "1", "descuento": "0", "retencion": "0", "re": "0", "n_lineas": "2",
            "concepto_0": "Trabajo", "cantidad_0": "2", "precio_0": "1.000,50", "iva_0": "21", "concepto_1": "Nota sin precio"}
    r = c.post("/e/1/guardar/F", data=form, follow_redirects=False)
    assert r.status_code == 303
    did = int(r.headers["location"].split("/")[2].split("?")[0])
    assert d_(con, did)["total"] == "2421.21"
    assert "Modificar" in c.get(f"/d/{did}").text
    assert "factura ya emitida" in c.get(f"/d/{did}/editar").text
    r = c.post(f"/d/{did}/cobro", data={"importe": "421,21", "fecha": "2026-03-11"}, follow_redirects=False)
    assert r.status_code == 303 and d_(con, did)["pendiente"] == "2000.00"
    assert "Cliente Web" in c.get("/e/1/pendientes").text
    assert c.get(f"/d/{did}/recibos").headers["content-type"] == "application/pdf"
    r = c.post(f"/d/{did}/cobro", data={"importe": "99999"})
    assert r.status_code == 400 and "superar" in r.text
    assert "Nota sin precio" in c.get(f"/d/{did}/rectificar").text
    r = c.post(f"/d/{did}/rectificar", data={**form, "rect_tipo": "I", "rect_motivo": "Error", "codigo_r": "R4",
                                             "precio_0": "-10"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Libros registro" in c.get("/e/1/libros?anio=2026&t=1").text
    assert c.get("/e/1/libros.xlsx?anio=2026&t=1").status_code == 200
    assert c.get("/e/1/libro_recibidas.csv?anio=2026").status_code == 200
    # borrar: exige confirmación
    a = nueva(con, "A", "2026-03-12")
    assert "definitivamente" in c.get(f"/d/{a}/borrar").text
    assert c.post(f"/d/{a}/borrar", data={}).status_code == 400
    assert c.post(f"/d/{a}/borrar", data={"confirmar": "1"}, follow_redirects=False).status_code == 303
    # pasar a factura
    a1, a2 = nueva(con, "A", "2026-03-12"), nueva(con, "A", "2026-03-13")
    assert "Pasar albaranes a factura" in c.get("/e/1/facturar?tipo=A").text
    r = c.post("/e/1/facturar", data={"ids": [str(a1), str(a2)], "fecha": "2026-03-31"}, follow_redirects=False)
    assert r.status_code == 303 and d_(con, a1)["facturado"] == 1
    for tipo in "FPAGM":
        assert c.get(f"/e/1/documentos?tipo={tipo}").status_code == 200
        assert c.get(f"/e/1/nuevo/{tipo}").status_code == 200

def test_web_asistente(con, cliente_web, tmp_path):
    c = cliente_web
    con.execute("DELETE FROM empresas"); con.commit()
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/bienvenida"
    assert "FactuCont" in c.get("/asistente").text
    assert c.post("/importar", data={"ruta": str(tmp_path / "no-existe")}).status_code == 400
    if FC5.exists():
        import shutil
        dst = tmp_path / "FC5"
        dst.mkdir()
        shutil.copy(FC5 / "formatos.ini", dst)
        shutil.copytree(FC5 / "00007", dst / "00007")
        r = c.post("/importar", data={"ruta": str(dst)})
        assert r.status_code == 200 and "Importación terminada" in r.text

# ------------------------------------------------------------------------------------- 6. instalador
def test_carpeta_de_datos(monkeypatch, tmp_path):
    import sys
    import app.db as m
    monkeypatch.delenv("CONTFACTU_DB", raising=False); monkeypatch.delenv("CONTFACTU_DATA", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert m.db_path() == tmp_path / "Roaming" / "ContFactu" / "contfactu.db"
    monkeypatch.setenv("CONTFACTU_DATA", str(tmp_path / "otra"))
    assert m.db_path() == tmp_path / "otra" / "contfactu.db"

def test_ficheros_de_empaquetado_sin_datos_reales():
    spec = (RAIZ / "instalador" / "ContFactu.spec").read_text(encoding="utf-8")
    iss = (RAIZ / "instalador" / "ContFactu.iss").read_text(encoding="utf-8")
    assert "templates" in spec and "datos" not in spec.split("datas")[1].split("]")[0]
    assert "{userappdata}" not in iss.lower() or "uninsneveruninstall" in iss.lower()
    for prohibido in (".db", ".dbf", "ejemplos", "capturas", "factucont/x"):
        assert prohibido not in iss.lower().replace("contfactu.exe", "")
    assert "{autodesktop}" in iss and "{group}" in iss
    assert (RAIZ / "instalador" / "construir.bat").exists()

def test_lanzador_puerto_libre():
    from app.__main__ import puerto_libre
    p = puerto_libre(8765)
    assert 1024 < p < 65536

def test_rectificativa_con_cabecera_corregida(con):
    """Rectificar un error en los datos del cliente (p. ej. NIF equivocado) por sustitución."""
    from app import repo
    f = nueva(con, nif="ERRONEO")
    with con: r = repo.crear_rectificativa(con, f, "S", "NIF del cliente erróneo", "R4", "2026-03-12",
                                           cabecera={"nif": "12345678Z", "nombre_f": "Cliente Uno, S.L."})
    d = d_(con, r)
    assert d["nif"] == "12345678Z" and d["nombre_f"] == "Cliente Uno, S.L." and d["total"] == "121.00"


# ---------------------------------------------------------------- asistente: origen elegido por el usuario
def _zip_fc5(tmp_path):
    import zipfile
    z = tmp_path / "copia_vm.zip"
    with zipfile.ZipFile(z, "w") as zz:
        for f in (FC5 / "00008").iterdir():
            if f.is_file():
                zz.write(f, f"FC5/00008/{f.name}")
    return z

def test_asistente_no_sugiere_ruta(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTFACTU_DB", str(tmp_path / "a.db"))
    from fastapi.testclient import TestClient
    from app.main import app
    h = TestClient(app).get("/asistente").text
    assert 'name="ruta" value=""' in h and 'name="archivo"' in h and "Binarema" not in h

def test_origen_errores(tmp_path):
    from app.origen import preparar, OrigenError
    for r in ("", str(tmp_path), str(tmp_path / "no_existe")):
        with pytest.raises(OrigenError): preparar(r)
    (tmp_path / "x.txt").write_text("hola")
    with pytest.raises(OrigenError): preparar(str(tmp_path / "x.txt"))

@pytest.mark.skipif(not FC5.exists(), reason="sin datos FactuCont")
def test_importar_desde_zip_ruta_y_subida(tmp_path, monkeypatch):
    from app.origen import preparar
    z = _zip_fc5(tmp_path)
    fc5, tmp = preparar(str(z))
    assert fc5.endswith("FC5") and tmp
    monkeypatch.setenv("CONTFACTU_DB", str(tmp_path / "b.db"))
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/importar", files={"archivo": ("copia_vm.zip", z.read_bytes(), "application/zip")}, data={"ruta": ""})
    assert r.status_code == 200 and "Importación terminada" in r.text and "00008" in r.text
    r = c.post("/importar", data={"ruta": str(z)})
    assert r.status_code == 200 and "Importación terminada" in r.text
    r = c.post("/importar", files={"archivo": ("x.7z", b"xx", "application/octet-stream")}, data={"ruta": ""})
    assert r.status_code == 400

RAR_REAL = Path(os.environ.get("CONTFACTU_RAR") or "/no-existe/copia.rar")

@pytest.mark.skipif(not RAR_REAL.exists(), reason="sin copia .rar de FactuCont")
def test_origen_rar_con_fc5_en_subcarpeta():
    import shutil
    from app.origen import preparar, _extractores_rar
    if not _extractores_rar():
        pytest.skip("sin extractor de RAR")
    fc5, tmp = preparar(str(RAR_REAL))
    try:
        assert os.path.basename(fc5) == "FC5" and os.path.isdir(os.path.join(fc5, "00008"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 0.0.2: versión, ventana propia, iconos, splash
def test_version_unica_y_visible(cliente_web):
    import app
    assert app.__version__ == "0.0.4"
    h = cliente_web.get("/acerca").text
    assert "ContFactu 0.0.4" in h and "LomoXSoft" in h
    assert cliente_web.get("/salud").text == "ContFactu OK 0.0.4"
    assert "<title>ContFactu 0.0.4</title>" in cliente_web.get("/asistente").text

def test_changelog_tiene_versiones():
    t = (Path(__file__).parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "0.0.1" in t and "0.0.2" in t and "0.0.3" in t and "0.0.4" in t

def test_iconos_svg_validos_y_en_menu(cliente_web, con):
    import xml.etree.ElementTree as ET
    from app import iconos
    for n in iconos.nombres():
        ET.fromstring(str(iconos.svg(n)))            # SVG bien formado
    assert iconos.svg("no_existe") == ""
    nueva(con)
    h = cliente_web.get("/e/1/documentos?tipo=F").text
    assert h.count('<svg class="ico"') >= 10 and "Libros IVA" in h

def test_splash_generado(tmp_path):
    from PIL import Image
    from herramientas.splash import generar
    p = generar(str(tmp_path / "s.png"), lado=200, ver="9.9.9")
    im = Image.open(p)
    assert im.size == (200, 200)

def test_splash_en_acerca(cliente_web):
    r = cliente_web.get("/splash.png")
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"

def test_mostrar_ventana_unica_instancia(cliente_web):
    from app.main import MOSTRAR
    assert cliente_web.post("/_mostrar").status_code == 409     # servidor sin ventana
    llamadas = []
    MOSTRAR["fn"] = lambda: llamadas.append(1)
    try:
        assert cliente_web.post("/_mostrar").status_code == 200 and llamadas == [1]
    finally:
        MOSTRAR["fn"] = None

class _Resp:
    def __init__(self, datos, cd): self.d, self.headers = datos, {"Content-Disposition": cd}
    def read(self): return self.d
    def __enter__(self): return self
    def __exit__(self, *a): return False

def test_puente_pdf_abre_visor_y_xlsx_guarda_con_dialogo(tmp_path, monkeypatch):
    import urllib.request
    from app.ventana import Puente
    pedidas = []
    def falso(url, timeout=0):
        pedidas.append(url)
        if url.endswith("/pdf"): return _Resp(b"%PDF-1.4", 'inline; filename="factura 260001.pdf"')
        return _Resp(b"PK\x03\x04", 'attachment; filename="libros_2026.xlsx"')
    monkeypatch.setattr(urllib.request, "urlopen", falso)
    abiertos = []
    destino = tmp_path / "elegido.xlsx"
    p = Puente("http://127.0.0.1:1", carpeta_tmp=str(tmp_path / "tmp"), abrir=abiertos.append, dialogo=lambda n: str(destino))
    r = p.abrir("/d/1/pdf")
    assert r["ok"] and abiertos and abiertos[0].endswith("factura 260001.pdf") and open(abiertos[0], "rb").read() == b"%PDF-1.4"
    r = p.guardar("/e/1/libros.xlsx?anio=2026")
    assert r["ok"] and destino.read_bytes() == b"PK\x03\x04" and "Guardado" in r["mensaje"]
    assert pedidas == ["http://127.0.0.1:1/d/1/pdf", "http://127.0.0.1:1/e/1/libros.xlsx?anio=2026"]
    p2 = Puente("http://127.0.0.1:1", dialogo=lambda n: None)
    assert p2.guardar("/e/1/libros.xlsx")["ok"] is False                 # cancelado
    assert p.abrir("http://otro.sitio/x")["ok"] is False                 # solo rutas locales

def test_plantilla_intercepta_descargas_en_ventana(cliente_web):
    h = cliente_web.get("/asistente").text
    assert "window.pywebview.api" in h and "guardar" in h and "abrir(" in h

def test_main_usa_navegador_si_falla_la_ventana(monkeypatch):
    """Sin WebView2/pywebview: arranca servidor y abre el navegador; con ventana: al cerrarla se para el servidor."""
    import app.__main__ as M, app.ventana as V, webbrowser
    abiertos = []
    monkeypatch.setenv("CONTFACTU_PORT", "8899"); monkeypatch.delenv("CONTFACTU_NO_BROWSER", raising=False)
    monkeypatch.setattr(M, "es_contfactu", lambda p: False)
    monkeypatch.setattr(webbrowser, "open", abiertos.append)
    estado = {}
    def ventana_ok(url, titulo, al_cargar=None, registrar_mostrar=None):
        estado["titulo"] = titulo; al_cargar(); registrar_mostrar(lambda: None)
    monkeypatch.setattr(V, "webview2_instalado", lambda: True)
    monkeypatch.setattr(V, "abrir_ventana", ventana_ok)
    M.main()                                         # vuelve al "cerrar la ventana"
    assert estado["titulo"] == "ContFactu 0.0.4" and abiertos == []
    import time, urllib.request
    time.sleep(0.3)
    with pytest.raises(Exception):                   # servidor detenido al cerrar la ventana
        urllib.request.urlopen("http://127.0.0.1:8899/salud", timeout=1)
    # Si la ventana falla (p. ej. sin WebView2), se usa el navegador
    def ventana_mal(*a, **k): raise RuntimeError("sin WebView2")
    monkeypatch.setattr(V, "abrir_ventana", ventana_mal)
    import threading
    monkeypatch.setattr(threading.Thread, "join", lambda self, timeout=None: None)
    M.main()
    assert abiertos and abiertos[0].startswith("http://127.0.0.1:")


# ---------------------------------------------------------------- 0.0.3: primera pantalla y empresa desde cero
from app import repo
EMPRESA_DEMO = {"nombre": "Talleres Demo, S.L.", "nif": "b-1234567-4", "direccion": "C/ Ejemplo, 1", "cp": "28001",
                "ciudad": "Madrid", "provincia": "Madrid", "telefono": "910000000", "email": "demo@example.com",
                "codigo": "", "serie_defecto": "", "contador_inicial": "", "ivas": "21, 10, 4, 0"}

def test_primer_arranque_ofrece_importar_o_empezar(cliente_web, con):
    con.execute("DELETE FROM empresas"); con.commit()          # instalación nueva: base vacía
    r = cliente_web.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/bienvenida"
    h = cliente_web.get("/bienvenida").text
    assert 'href="/empresas/nueva"' in h and 'href="/asistente"' in h and "Empezar desde cero" in h
    # desde el asistente se puede volver atrás sin importar nada
    assert 'href="/bienvenida"' in cliente_web.get("/asistente").text
    f = cliente_web.get("/empresas/nueva").text
    assert 'name="nif"' in f and 'value="00001"' in f and 'name="logo"' in f

def test_crear_empresa_desde_cero_y_trabajar(cliente_web, con):
    r = cliente_web.post("/empresas/nueva", data=EMPRESA_DEMO, follow_redirects=False)
    assert r.status_code == 303, r.text
    eid = int(r.headers["location"].split("/")[2])
    e = repo.empresa(con, eid)
    assert e["codigo"] == "00001" and e["nif"] == "B12345674" and e["origen"] == "nuevo" and e["ivas"] == "21,10,4,0"
    assert "creada" in cliente_web.get(r.headers["location"]).text
    assert cliente_web.get("/", follow_redirects=False).status_code == 200          # ya no va a la bienvenida
    # cliente y proveedor
    r = cliente_web.post(f"/e/{eid}/clientes/guardar", data={"nombre": "Cliente Demo", "nif": "12345678Z", "ciudad": "28002 Madrid",
                                                             "forma_pago": "Transferencia"}, follow_redirects=False)
    assert r.status_code == 303
    c = con.execute("SELECT * FROM clientes WHERE empresa_id=?", (eid,)).fetchone()
    assert c["codigo"] == "00001" and c["nombre"] == "Cliente Demo"
    assert cliente_web.post(f"/e/{eid}/proveedores/guardar", data={"nombre": "Proveedor Demo", "retencion": "15"},
                            follow_redirects=False).status_code == 303
    assert "Proveedor Demo" in cliente_web.get(f"/e/{eid}/proveedores").text
    assert "Cliente Demo" in cliente_web.get(f"/e/{eid}/clientes/{c['id']}").text
    # el formulario propone el IVA por defecto de la empresa y el cliente elegido
    h = cliente_web.get(f"/e/{eid}/nueva?cliente=00001").text
    assert 'value="Cliente Demo"' in h and 'IVA_DEF="21"' in h
    # factura con numeración AA + correlativo, PDF con el diseño por defecto, libros de IVA
    did, num = repo.crear_factura(con, eid, {"fecha": "2026-11-02", "nombre_f": "Cliente Demo", "nif": "12345678Z"},
                                  [L("Reparación", "2", "50")])
    con.commit()
    assert num == "260001"
    pdf = cliente_web.get(f"/d/{did}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    t = _texto_pdf(pdf.content)
    if t:
        assert "Talleres Demo" in t and "B12345674" in t and "260001" in t and "121,00" in t
    assert cliente_web.get(f"/e/{eid}/libros?anio=2026").status_code == 200
    assert cliente_web.get(f"/e/{eid}/libros.xlsx?anio=2026").content[:2] == b"PK"
    assert cliente_web.get(f"/d/{did}/recibos").content[:4] == b"%PDF"

def test_empresa_serie_y_primer_numero(con):
    from app import altas
    eid = altas.crear_empresa(con, dict(EMPRESA_DEMO, serie_defecto="a", contador_inicial="57"))
    assert repo.siguiente_numero(con, eid, "F", "A", "2026-05-01") == "A"[:0] + "260057"
    did, num = repo.crear_factura(con, eid, {"fecha": "2026-05-01", "serie": "A", "nombre_f": "X"}, [L("x", 1, 10)])
    assert num == "260057"
    assert repo.siguiente_numero(con, eid, "F", "A", "2026-05-02") == "260058"
    assert repo.siguiente_numero(con, eid, "F", "A", "2027-01-02") == "270001"       # cada año vuelve a 1
    assert repo.siguiente_numero(con, eid, "F", "", "2026-05-02") == "260001"        # otra serie empieza en 1
    assert repo.siguiente_numero(con, eid, "P", "", "2026-05-02") == "260001"

def test_empresa_validaciones(con):
    from app import altas
    for cambio, texto in [({"nombre": ""}, "nombre"), ({"nif": "B12345678"}, "no es válido"), ({"cp": "123"}, "postal"),
                          ({"email": "x@"}, "correo"), ({"serie_defecto": "R"}, "rectificativas"), ({"ivas": "21, abc"}, "IVA"),
                          ({"contador_inicial": "0"}, "primer número"), ({"codigo": "ABC"}, "código")]:
        with pytest.raises(repo.ErrorNegocio, match=texto):
            altas.crear_empresa(con, dict(EMPRESA_DEMO, **cambio))
    altas.crear_empresa(con, EMPRESA_DEMO)
    with pytest.raises(repo.ErrorNegocio, match="ya lo usa"):
        altas.crear_empresa(con, dict(EMPRESA_DEMO, codigo="1"))
    assert altas.siguiente_codigo_empresa(con) == "00002"     # 00001 la nueva; 99999 la de la prueba
    assert altas.nif_valido("X1234567L") and altas.nif_valido("Q2826000H") and not altas.nif_valido("12345678A")

def test_formulario_empresa_muestra_error_sin_perder_datos(cliente_web):
    r = cliente_web.post("/empresas/nueva", data=dict(EMPRESA_DEMO, nif="B12345678"))
    assert r.status_code == 400 and "no es válido" in r.text and "Talleres Demo" in r.text

def test_editar_empresa_y_logo(cliente_web, con, tmp_path, monkeypatch):
    import io
    from PIL import Image
    monkeypatch.setenv("CONTFACTU_DATA", str(tmp_path / "datos"))
    b = io.BytesIO(); Image.new("RGB", (120, 40), "navy").save(b, "PNG")
    r = cliente_web.post("/empresas/nueva", data=EMPRESA_DEMO, files={"logo": ("logo.png", b.getvalue(), "image/png")},
                         follow_redirects=False)
    eid = int(r.headers["location"].split("/")[2])
    assert (tmp_path / "datos" / "logos" / f"empresa_{eid}.png").exists()       # en la carpeta de datos
    assert cliente_web.get(f"/e/{eid}/logo").content[:4] == b"\x89PNG"
    r = cliente_web.post(f"/e/{eid}/empresa", data=dict(EMPRESA_DEMO, nombre="Talleres Demo Dos, S.L.", codigo="00001"),
                         follow_redirects=False)
    assert r.status_code == 303 and repo.empresa(con, eid)["nombre"] == "Talleres Demo Dos, S.L."
    did, _ = repo.crear_factura(con, eid, {"fecha": "2026-11-02", "nombre_f": "C"}, [L("x", 1, 10)]); con.commit()
    assert cliente_web.get(f"/d/{did}/pdf").content[:4] == b"%PDF"                 # con logotipo
    r = cliente_web.post("/empresas/nueva", data=EMPRESA_DEMO, files={"logo": ("x.png", b"no es imagen", "image/png")})
    assert r.status_code == 400 and "imagen" in r.text

def test_importar_no_mezcla_con_empresa_creada(con, tmp_path):
    from app import altas, importer
    eid = altas.crear_empresa(con, EMPRESA_DEMO)           # código 00001
    fc5 = tmp_path / "FC5" / "00001"; fc5.mkdir(parents=True)
    res = importer.importar_fc5(con, str(tmp_path / "FC5"), ["00001"])
    assert res[0][2].get("omitida") and "ya lo usa" in res[0][2]["omitida"]
    assert repo.empresa(con, eid)["nombre"] == "Talleres Demo, S.L." and repo.empresa(con, eid)["origen"] == "nuevo"

def test_menu_permite_nueva_empresa_e_importar_siempre(cliente_web, con):
    nueva(con)
    h = cliente_web.get("/").text
    assert 'href="/empresas/nueva"' in h and 'href="/asistente"' in h
    h = cliente_web.get("/e/1/documentos?tipo=F").text
    assert "Cambiar de empresa" in h and 'href="/e/1/empresa"' in h and 'href="/e/1/proveedores"' in h

def test_datos_nunca_junto_al_programa(monkeypatch, tmp_path):
    """En el .exe (C:\\Program Files\\ContFactu) los datos, el log y el perfil WebView2 van a %APPDATA%\\ContFactu."""
    import sys
    from app import db, ventana
    monkeypatch.delenv("CONTFACTU_DATA", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert db.data_dir() == tmp_path / "Roaming" / "ContFactu"
    assert ventana.carpeta_webview().startswith(str(tmp_path / "Roaming" / "ContFactu"))


# ---------------------------------------------------------------- logotipo: se encaja sin recortar ni deformar
@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="sin pdftoppm (poppler)")
@pytest.mark.parametrize("w,h", [(1200, 100), (100, 1200), (400, 400), (3000, 2000)])
def test_logo_encaja_sin_recortar(tmp_path, w, h):
    import io, subprocess
    from PIL import Image, ImageChops
    from app.fmt_pdf import render_pdf_defecto
    b = io.BytesIO(); Image.new("RGB", (w, h), (255, 0, 0)).save(b, "PNG"); b.seek(0)
    pdf = render_pdf_defecto({"nombre": "Demo", "nif": "B12345674"},
                             {"tipo": "F", "numero": "260001", "fecha": "2026-11-02", "total": "0"}, [], [], logo=b)
    (tmp_path / "a.pdf").write_bytes(pdf)
    subprocess.run(["pdftoppm", "-r", "144", "-png", "-singlefile", str(tmp_path / "a.pdf"), str(tmp_path / "a")], check=True)
    r, g, _ = Image.open(tmp_path / "a.png").convert("RGB").split()
    caja = ImageChops.multiply(Image.eval(r, lambda v: 255 if v > 200 else 0), Image.eval(g, lambda v: 255 if v < 60 else 0)).getbbox()
    ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
    assert ancho <= 45 / 25.4 * 144 + 2 and alto <= 22 / 25.4 * 144 + 2          # cabe en 45 × 22 mm
    assert abs(ancho / alto - w / h) / (w / h) < 0.12                           # misma proporción: ni recorte ni deformación
