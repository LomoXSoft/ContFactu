"""Pruebas de la 0.0.4: IVA sin límites, copias de seguridad, actualización segura, correo, Excel y avisos de cobro.
Todo con datos ficticios en carpetas temporales."""
import datetime, importlib, io, json, os, shutil, sqlite3, subprocess, zipfile
from decimal import Decimal as D
from pathlib import Path
import pytest

DATOS_TEST = Path(__file__).resolve().parent / "esquemas"

@pytest.fixture()
def entorno(tmp_path, monkeypatch):
    """Carpeta de datos temporal (CONTFACTU_DATA) y base dentro de ella; módulos recargados."""
    datos = tmp_path / "datos"
    monkeypatch.setenv("CONTFACTU_DATA", str(datos))
    monkeypatch.delenv("CONTFACTU_DB", raising=False)
    import app.db
    importlib.reload(app.db)
    return datos

@pytest.fixture()
def con(entorno):
    import app.db
    c = app.db.connect()
    with c:
        c.execute("INSERT INTO empresas(id,codigo,nombre,nif,direccion,ciudad,ivas) VALUES(1,'99999','Empresa de Prueba SL','B00000000',"
                  "'C/ Falsa 1','Madrid','21,10,4,0')")
        c.execute("INSERT INTO clientes(empresa_id,codigo,nombre,nombre_f,nif,email) VALUES(1,'C1','Cliente Uno','Cliente Uno SL',"
                  "'12345678Z','cliente@example.com')")
    return c

@pytest.fixture()
def web(con):
    import app.main
    importlib.reload(app.main)
    from fastapi.testclient import TestClient
    return TestClient(app.main.app)

def L(concepto, cant, precio, iva="21", dto="0"):
    return {"concepto": concepto, "cantidad": str(cant), "precio": str(precio), "iva": str(iva), "descuento": dto}

def nueva(con, lineas, tipo="F", fecha="2026-03-10", **kw):
    from app import repo
    datos = {"fecha": fecha, "nombre_f": "Cliente Uno SL", "nif": "12345678Z", "cliente_codigo": "C1", **kw}
    with con:
        return repo.guardar_documento(con, 1, tipo, datos, lineas)

# ======================================================================================== 6. IVA sin límites
def test_tipo_iva_valido():
    from app.calc import tipo_iva_valido
    assert tipo_iva_valido("7,5") == "7.5" and tipo_iva_valido("21") == "21" and tipo_iva_valido(" 5,25 %") == "5.25"
    assert tipo_iva_valido("0") == "0" and tipo_iva_valido("100") == "100" and tipo_iva_valido("10.00") == "10"
    assert tipo_iva_valido("7,555") == "7.555"
    for malo in ("abc", "", "NaN"):
        with pytest.raises(ValueError, match="no es válido"):
            tipo_iva_valido(malo)
    for malo in ("-1", "100,01", "150", "-0,01", "1e3"):
        with pytest.raises(ValueError, match="entre 0 % y 100 %"):
            tipo_iva_valido(malo)

def test_formato_pct_no_revienta_con_lo_que_escribe_el_usuario():
    from app.calc import formato_pct
    assert formato_pct("5,2") == "5,2" and formato_pct("5.2") == "5,2" and formato_pct(" 7,5 %") == "7,5"
    assert formato_pct("21") == "21" and formato_pct(None) == "" and formato_pct("") == ""
    assert formato_pct("abc") == "abc" and formato_pct("150") == "150" and formato_pct("5,2 %") == "5,2"

def test_factura_con_iva_7_5_y_cinco_tipos(con):
    from app import repo
    from app.calc import totales_cabecera
    did = nueva(con, [L("A", 1, 100, "21"), L("B", 1, 100, "10"), L("C", 1, 100, "7,5"), L("D", 1, 100, "4"), L("E", 1, 100, "0"),
                      L("F", 2, 50, "7.5")])
    d = repo.doc(con, did)
    t = totales_cabecera(d)
    assert [(str(x["iva"]), str(x["base"]), str(x["cuota_iva"])) for x in t["desglose"]] == [
        ("21", "100.00", "21.00"), ("10", "100.00", "10.00"), ("7.5", "200.00", "15.00"), ("4", "100.00", "4.00"), ("0", "100.00", "0.00")]
    assert d["total"] == "650.00" and d["pendiente"] == "650.00"
    # compatibilidad: los tres primeros tipos siguen en base1..3
    assert (d["base1"], d["iva1"], d["base3"], d["iva3"]) == ("100.00", "21", "200.00", "7.5")
    assert len(json.loads(d["desglose_iva"])) == 5
    _, ls, _ = repo.documento(con, did)
    assert {l["iva"] for l in ls} == {"21", "10", "7.5", "4", "0"}

def test_iva_fuera_de_rango_se_rechaza(con):
    from app import repo
    from app.repo import ErrorNegocio
    for malo in ("101", "-4", "150"):
        with pytest.raises(ErrorNegocio, match="entre 0 % y 100 %") as exc:
            nueva(con, [L("A", 1, 100, malo)])
        assert exc.value.campo == "iva" and exc.value.indice == 0
    with pytest.raises(ErrorNegocio, match="no es válido") as exc:
        nueva(con, [L("A", 1, 100, "veintiuno")])
    assert exc.value.campo == "iva"
    with pytest.raises(ErrorNegocio, match="El descuento debe estar entre 0 % y 100 %") as exc:
        nueva(con, [L("A", 1, 100, "21", "101")])
    assert exc.value.campo == "descuento" and exc.value.indice == 0
    did = nueva(con, [L("A", 1, 100, "7,555", "12,5")])
    d, ls, _ = repo.documento(con, did)
    assert ls[0]["iva"] == "7.555" and ls[0]["descuento"] == "12.5"

def test_documento_antiguo_sin_desglose_sigue_igual(con):
    from app.calc import totales_cabecera
    t = totales_cabecera({"base1": "100", "iva1": "21", "re1": "5.2", "base2": "50", "iva2": "10", "re2": "1.4"})
    assert t["total"] == D("181.90") and len(t["desglose"]) == 2

def test_recargo_editable_por_empresa(con):
    from app import repo
    with con:
        con.execute("UPDATE empresas SET re_tasas='21:5.2,7.5:1,10:1.4' WHERE id=1")
    did = nueva(con, [L("A", 1, 100, "7,5"), L("B", 1, 100, "21"), L("C", 1, 100, "4")], re=True)
    t = repo.totales_cabecera(repo.doc(con, did))
    re = {str(x["iva"]): (str(x["re"]), str(x["cuota_re"])) for x in t["desglose"]}
    assert re == {"21": ("5.2", "5.20"), "7.5": ("1", "1.00"), "4": ("0", "0.00")}   # 4 % sin recargo definido -> 0
    assert repo._con_re(repo.doc(con, did))

def test_libro_y_resumen_con_tipos_arbitrarios(con):
    from app import repo
    nueva(con, [L("A", 1, 100, "21"), L("B", 1, 100, "10"), L("C", 1, 100, "7,5"), L("D", 1, 100, "4"), L("E", 1, 100, "5")])
    filas = repo.libro(con, 1, "emitidas", "2026", "1")
    assert len(filas) == 5 and filas[0]["total"] == D("547.50") and all(f["total"] == 0 for f in filas[1:])
    r = repo.resumen_libro(filas)
    assert r["cuota_iva"] == D("47.50") and r["facturas"] == 1
    m = repo.resumen_303(con, 1, "2026", "1")
    assert {str(x["iva"]) for x in m["otros"]} == {"7.5", "5"} and m["c27"] == D("47.50")

def _texto_pdf(data, tmp_path):
    if not shutil.which("pdftotext"):
        pytest.skip("sin pdftotext")
    p = tmp_path / "x.pdf"; p.write_bytes(data)
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout

def test_pdf_por_defecto_con_cinco_tipos(con, tmp_path):
    from app import repo
    from app.fmt_pdf import render_pdf_defecto
    did = nueva(con, [L("A", 1, 100, "21"), L("B", 1, 100, "10"), L("C", 1, 100, "7,5"), L("D", 1, 100, "4"), L("E", 1, 100, "0")])
    d, ls, ps = repo.documento(con, did)
    txt = _texto_pdf(render_pdf_defecto(repo.empresa(con, 1), d, ls, ps), tmp_path)
    for x in ("21%", "10%", "7,5%", "4%", "0%", "7,50", "542,50"):
        assert x in txt, x

FMT_MINIMO = """[Documento]
PapelAncho=210
PapelAlto=297
Superior=10
Inferior=10
Izquierdo=10
[Banda0]
Alto=150
[Banda1]
Alto=6
[Banda2]
Alto=60
[Objeto1]
Tipo=2
Banda=0
Campo=F>NUMERO
PosX=10
PosY=10
TamX=40
TamY=6
[Objeto2]
Tipo=2
Banda=2
Campo=BASE_DOC
PosX=10
PosY=5
TamX=30
TamY=12
Alineación=1
[Objeto3]
Tipo=2
Banda=2
Campo=%IVA_DOC
PosX=45
PosY=5
TamX=15
TamY=12
Alineación=1
[Objeto4]
Tipo=2
Banda=2
Campo=IVA_DOC
PosX=65
PosY=5
TamX=30
TamY=12
Alineación=1
[Objeto5]
Tipo=2
Banda=2
Campo=TOTAL_DOC
PosX=120
PosY=5
TamX=30
TamY=6
Alineación=1
"""

def test_pdf_diseno_factucont_con_mas_de_tres_tipos(con, tmp_path):
    """Los diseños .fmt de FactuCont preveían 3 tipos: con más, se imprimen todos (letra más pequeña), sin cortar ninguno."""
    from app import repo
    from app.fmt_pdf import render_pdf
    did = nueva(con, [L("A", 1, 100, "21"), L("B", 1, 100, "10"), L("C", 1, 100, "7,5"), L("D", 1, 100, "4"), L("E", 1, 100, "5")])
    d, ls, ps = repo.documento(con, did)
    txt = _texto_pdf(render_pdf(FMT_MINIMO, repo.empresa(con, 1), d, ls, ps), tmp_path)
    for x in ("21", "10", "7,5", "4", "5", "7,50", "547,50"):
        assert x in txt, x
    assert txt.count("100,00") == 5 and "260001" in txt

def test_formulario_empresa_tabla_de_tipos(web, con):
    from app import altas
    r = web.post("/e/1/empresa", data={"nombre": "Empresa de Prueba SL", "nif": "B00000000", "codigo": "99999",
                                        "tipo_iva": ["21", "7,5", "10", ""], "tipo_re": ["5,2", "1", "", ""]}, follow_redirects=False)
    assert r.status_code == 303, r.text[:500]
    e = dict(con.execute("SELECT * FROM empresas WHERE id=1").fetchone())
    assert e["ivas"] == "21,7.5,10" and e["re_tasas"] == "21:5.2,7.5:1"
    assert altas.tabla_tipos(e)[:2] == [("21", "5.2"), ("7.5", "1")]
    h = web.get("/e/1/empresa").text
    assert 'value="7,5"' in h and "Añadir tipo" in h
    r = web.post("/e/1/empresa", data={"nombre": "Empresa de Prueba SL", "nif": "B00000000", "codigo": "99999",
                                        "tipo_iva": ["21", "150"], "tipo_re": ["", ""]})
    assert r.status_code == 400 and "entre 0 % y 100 %" in r.text and 'value="150"' in r.text
    assert 'name="tipo_iva"' in r.text and 'id="err-tipo_iva-1"' in r.text and 'aria-invalid="true"' in r.text
    r = web.post("/e/1/empresa", data={"nombre": "Empresa de Prueba SL", "nif": "B00000000", "codigo": "99999",
                                        "tipo_iva": ["21", "21"], "tipo_re": ["", ""]})
    assert r.status_code == 400 and "repetido" in r.text

def test_re_render_empresa_con_nif_malo_y_comas_no_da_500(web, con):
    """Un NIF rechazado no puede dejar la ventana en «Internal Server Error» al volver a pintar los tipos."""
    from app import repo
    datos = {"nombre": "Empresa Nueva SL", "nif": "TEST", "codigo": "00002", "contador_inicial": "1",
             "tipo_iva": ["21", "7,5", ""], "tipo_re": ["5,2", "1,4", ""]}
    for url in ("/empresas/nueva", "/e/1/empresa"):
        cuerpo = dict(datos, codigo="99999" if url != "/empresas/nueva" else "00002",
                      nombre="Empresa de Prueba SL" if url != "/empresas/nueva" else datos["nombre"])
        r = web.post(url, data=cuerpo)
        assert r.status_code == 400, r.text[:400]
        assert "Internal Server Error" not in r.text
        assert 'id="err-nif"' in r.text and 'aria-describedby="err-nif"' in r.text
        assert 'name="nif"' in r.text and 'aria-invalid="true"' in r.text
        assert 'id="err-cp"' not in r.text
        assert "no es válido" in r.text
        assert 'value="5,2"' in r.text and 'value="7,5"' in r.text and 'value="1,4"' in r.text
        assert "Crear empresa" in r.text or "Guardar" in r.text
    cp = web.post("/empresas/nueva", data={"nombre": "Empresa Nueva SL", "nif": "B12345674", "codigo": "00004",
                                           "cp": "123", "contador_inicial": "1", "tipo_iva": ["21"], "tipo_re": ["5,2"]})
    assert cp.status_code == 400 and "Internal Server Error" not in cp.text
    assert 'id="err-cp"' in cp.text and "5 cifras" in cp.text and 'aria-describedby="err-cp"' in cp.text
    assert 'id="err-nif"' not in cp.text and 'value="5,2"' in cp.text
    raro = web.post("/empresas/nueva", data={"nombre": "Empresa Nueva SL", "nif": "B12345674", "codigo": "00003",
                                             "contador_inicial": "1", "tipo_iva": ["21", "abc", ""],
                                             "tipo_re": ["", "texto", ""]})
    assert raro.status_code == 400 and "Internal Server Error" not in raro.text
    assert 'value="abc"' in raro.text and 'value="texto"' in raro.text and 'id="err-tipo_iva-1"' in raro.text
    assert "no es válido" in raro.text
    ok = web.post("/empresas/nueva", data={"nombre": "Empresa Nueva SL", "nif": "B12345674", "codigo": "00002",
                                           "contador_inicial": "1", "tipo_iva": ["21", "10"],
                                           "tipo_re": ["5,2", "1,4"]}, follow_redirects=False)
    assert ok.status_code == 303, ok.text[:400]
    e = repo.empresa(con, con.execute("SELECT id FROM empresas WHERE codigo='00002'").fetchone()[0])
    assert e["re_tasas"] == "21:5.2,10:1.4" and e["ivas"] == "21,10"

def test_factura_y_cliente_avisan_en_el_campo(web):
    r = web.post("/e/1/guardar/F", data={"fecha": "2026-03-10", "nombre_f": "Cliente Web", "n_lineas": "1",
                                         "concepto_0": "Libro", "cantidad_0": "1", "precio_0": "100", "iva_0": "150",
                                         "descuento_0": "0", "descuento": "0", "retencion": "0"})
    assert r.status_code == 400 and 'id="err-iva-0"' in r.text and "El IVA debe estar entre 0 % y 100 %" in r.text
    assert "Libro" in r.text and "Internal Server Error" not in r.text
    r = web.post("/e/1/guardar/F", data={"fecha": "2026-03-10", "nombre_f": "Cliente Web", "n_lineas": "1",
                                         "concepto_0": "Libro", "cantidad_0": "1", "precio_0": "100", "iva_0": "21",
                                         "descuento_0": "120", "descuento": "0", "retencion": "0"})
    assert r.status_code == 400 and 'id="err-descuento-0"' in r.text and 'data-indice="0"' in r.text
    r = web.post("/e/1/guardar/F", data={"fecha": "2026-03-10", "nombre_f": "Cliente Web", "n_lineas": "1",
                                         "concepto_0": "Libro", "cantidad_0": "1", "precio_0": "100", "iva_0": "21",
                                         "descuento_0": "10,5", "descuento": "101", "retencion": "0"})
    assert r.status_code == 400 and 'id="err-descuento"' in r.text and 'aria-describedby="err-descuento"' in r.text
    assert 'id="err-descuento-0"' not in r.text
    r = web.post("/e/1/clientes/guardar", data={"nombre": "Con descuento", "codigo": "C9", "descuento": "150,5"})
    assert r.status_code == 400 and 'id="err-descuento"' in r.text and "El descuento debe estar entre 0 % y 100 %" in r.text
    assert 'value="150,5"' in r.text or "150,5" in r.text

def test_formulario_factura_iva_libre(web, con):
    form = {"fecha": "2026-03-10", "nombre_f": "Cliente Web", "nif": "1", "descuento": "0", "retencion": "0", "re": "0",
            "n_lineas": "2", "concepto_0": "Libro", "cantidad_0": "1", "precio_0": "100", "iva_0": "7,5",
            "concepto_1": "Otro", "cantidad_1": "1", "precio_1": "100", "iva_1": "21 %"}
    r = web.post("/e/1/guardar/F", data=form, follow_redirects=False)
    assert r.status_code == 303
    did = int(r.headers["location"].split("/")[2].split("?")[0])
    from app import repo
    assert repo.doc(con, did)["total"] == "228.50"
    h = web.get("/e/1/nuevo/F").text
    assert 'list="ivas"' in h and 'min="0"' in h and 'max="100"' in h

# ======================================================================================== 1. copias de seguridad
def _logo(entorno):
    (entorno / "logos").mkdir(parents=True, exist_ok=True)
    (entorno / "logos" / "empresa_1.png").write_bytes(b"\x89PNG demo")

def test_copia_un_clic(con, entorno, tmp_path):
    from app import copias, db
    _logo(entorno)
    nueva(con, [L("A", 1, 100)])
    destino = tmp_path / "Mis copias #1 (100%)"
    ruta = copias.crear_copia(con, str(destino))
    assert ruta.parent == destino and ruta.name.startswith("ContFactu-copia-") and ruta.suffix == ".zip"
    with zipfile.ZipFile(ruta) as z:
        assert set(z.namelist()) == {"contfactu.db", "logos/empresa_1.png", "contfactu-copia.json"}
        man = json.loads(z.read("contfactu-copia.json"))
        assert man["empresas"] == 1 and man["documentos"] == 1 and man["version_programa"] == importlib.import_module("app").__version__
    assert db.ajuste(con, "copia_carpeta") == str(destino)
    assert copias.dias_desde_ultima(con) == 0 and not copias.necesita_aviso(con)
    # una segunda copia en el mismo segundo no pisa la primera
    ruta2 = copias.crear_copia(con)       # sin carpeta: usa la última
    assert ruta2 != ruta and ruta2.parent == destino
    assert not list(destino.glob("*.part"))

def test_carpeta_por_defecto_en_documentos(con):
    from app import copias
    assert copias.carpeta_defecto().name == "ContFactu-Copias" and copias.carpeta_defecto().parent.name in ("Documents", "Documentos")

def test_recordatorio_de_copia(con):
    from app import copias, db
    assert copias.necesita_aviso(con)                     # nunca se ha hecho
    with con:
        db.poner_ajuste(con, "copia_ultima", (datetime.datetime.now() - datetime.timedelta(days=8)).isoformat(timespec="seconds"))
    assert copias.dias_desde_ultima(con) == 8 and copias.necesita_aviso(con)
    with con:
        db.poner_ajuste(con, "copia_dias", 10)
    assert not copias.necesita_aviso(con)
    with con:
        db.poner_ajuste(con, "copia_dias", 0)              # 0 = no avisar
        db.poner_ajuste(con, "copia_ultima", None)
    assert not copias.necesita_aviso(con)

def test_restaurar_con_copia_previa(con, entorno, tmp_path):
    from app import copias, repo
    import app.db
    _logo(entorno)
    nueva(con, [L("Original", 1, 100)])
    ruta = copias.crear_copia(con, str(tmp_path / "c"))
    nueva(con, [L("Posterior", 1, 50)])                  # cambio después de la copia
    (entorno / "logos" / "empresa_1.png").unlink()
    (entorno / "logos" / "otro.png").write_bytes(b"x")
    info, previa = copias.restaurar(ruta)
    assert info["documentos"] == 1
    c2 = app.db.connect()
    assert c2.execute("SELECT COUNT(*) FROM documentos").fetchone()[0] == 1
    assert sorted(p.name for p in (entorno / "logos").iterdir()) == ["empresa_1.png"]
    # la copia de seguridad previa tiene los datos que había antes de restaurar
    assert previa.parent == entorno / "copias-automaticas" and "antes-de-restaurar" in previa.name
    assert copias.leer_copia(previa)["documentos"] == 2

def test_restaurar_rechaza_archivos_que_no_son_copias(con, tmp_path):
    from app import copias
    malo = tmp_path / "malo.zip"
    with zipfile.ZipFile(malo, "w") as z:
        z.writestr("otra.txt", "hola")
    with pytest.raises(copias.ErrorCopia, match="no es una copia"):
        copias.leer_copia(malo)
    (tmp_path / "roto.zip").write_bytes(b"no es zip")
    with pytest.raises(copias.ErrorCopia, match="no es un .zip"):
        copias.leer_copia(tmp_path / "roto.zip")
    dañado = tmp_path / "danado.zip"
    with zipfile.ZipFile(dañado, "w") as z:
        z.writestr("contfactu.db", b"SQLite format 3\x00" + b"\x00" * 200)
    with pytest.raises(copias.ErrorCopia):
        copias.leer_copia(dañado)

def test_restaurar_ignora_rutas_peligrosas(con, entorno, tmp_path):
    from app import copias
    ruta = copias.crear_copia(con, str(tmp_path / "c"))
    with zipfile.ZipFile(ruta, "a") as z:
        z.writestr("logos/../../fuera.txt", "x")
        z.writestr("../fuera2.txt", "x")
    copias.restaurar(ruta)
    assert not (entorno.parent / "fuera.txt").exists() and not (tmp_path / "fuera2.txt").exists()

def test_copias_web_crear_revisar_y_restaurar(web, con, entorno, tmp_path):
    h = web.get("/e/1/documentos?tipo=F").text
    assert "Todavía no ha hecho ninguna copia" in h and "Hacer copia ahora" in h
    r = web.post("/copias/crear", data={"carpeta": str(tmp_path / "web")}, follow_redirects=False)
    assert r.status_code == 303
    assert "ninguna copia" not in web.get("/e/1/documentos?tipo=F").text
    zipf = next((tmp_path / "web").glob("*.zip"))
    nueva(con, [L("Después", 1, 1)])
    # revisar (subiendo el archivo): no cambia nada todavía
    with open(zipf, "rb") as fh:
        r = web.post("/copias/restaurar/revisar", files={"archivo": (zipf.name, fh, "application/zip")})
    assert r.status_code == 200 and "¿Restaurar esta copia?" in r.text and "Empresa de Prueba SL" in r.text
    assert con.execute("SELECT COUNT(*) FROM documentos").fetchone()[0] == 1
    token = r.text.split('name="token" value="')[1].split('"')[0]
    r = web.post("/copias/restaurar", data={"token": token})            # sin confirmar
    assert r.status_code == 400 and con.execute("SELECT COUNT(*) FROM documentos").fetchone()[0] == 1
    r = web.post("/copias/restaurar", data={"token": token, "confirmar": "1"})
    assert r.status_code == 200 and "Copia restaurada" in r.text and "antes-de-restaurar" in r.text
    import app.db
    assert app.db.connect().execute("SELECT COUNT(*) FROM documentos").fetchone()[0] == 0
    r = web.post("/copias/restaurar", data={"token": token, "confirmar": "1"})   # el token no se reutiliza
    assert r.status_code == 400

def test_copias_web_ajustes_y_recordar_luego(web, con):
    assert web.post("/copias/ajustes", data={"dias": "3"}, follow_redirects=False).status_code == 303
    from app import db
    assert db.ajuste(con, "copia_dias") == "3"
    assert web.post("/copias/ajustes", data={"dias": "-1"}).status_code == 400
    web.post("/copias/recordar-luego", follow_redirects=False)
    assert "Hacer copia ahora</button></form>\n<a href=\"/copias\"" not in web.get("/e/1/documentos?tipo=F").text
    assert "ninguna copia" not in web.get("/e/1/documentos?tipo=F").text

# ======================================================================================== 5. actualización segura
def _base_antigua(ruta, esquema):
    c = sqlite3.connect(ruta)
    c.executescript((DATOS_TEST / esquema).read_text(encoding="utf-8"))
    c.execute("INSERT INTO empresas(id,codigo,nombre,nif) VALUES(1,'00001','Antigua SL','B00000000')")
    c.execute("""INSERT INTO documentos(id,empresa_id,tipo,numero_raw,serie,numero,fecha,nombre_f,base1,iva1,re1,base2,iva2,re2,
                 total,pendiente,origen) VALUES(1,1,'F','   230001','','230001','2023-05-02','Cliente','100','21','0','50','10','0',
                 '176.00','176.00','factucont')""")
    c.execute("INSERT INTO lineas(documento_id,orden,concepto,cantidad,precio,descuento,iva) VALUES(1,1,'A','1','100','0','21')")
    c.execute("INSERT INTO lineas(documento_id,orden,concepto,cantidad,precio,descuento,iva) VALUES(1,2,'B','1','50','0','10')")
    c.commit(); c.close()

@pytest.mark.parametrize("esquema", ["esquema_0.0.1.sql", "esquema_0.0.3.sql"])
def test_migracion_desde_version_antigua(entorno, esquema):
    import app.db
    from app import repo, copias
    entorno.mkdir(parents=True)
    ruta = entorno / "contfactu.db"
    _base_antigua(ruta, esquema)
    original = ruta.read_bytes()
    assert app.db.version_datos(ruta) == (None, None)
    c = app.db.connect()
    # 1) copia automática ANTES de migrar, con la base tal cual estaba
    autos = list((entorno / "copias-automaticas").glob(f"ContFactu-antes-de-{importlib.import_module('app').__version__}-*.zip"))
    assert len(autos) == 1
    with zipfile.ZipFile(autos[0]) as z:
        tmp = entorno / "x.db"; tmp.write_bytes(z.read("contfactu.db"))
    v = sqlite3.connect(tmp)
    cols = {r[1] for r in v.execute("PRAGMA table_info(empresas)")}
    v.close()
    assert "re_tasas" not in cols                       # es la base anterior, sin migrar
    # 2) versión y esquema guardados; columnas y tablas nuevas presentes
    assert app.db.version_datos(ruta) == (importlib.import_module("app").__version__, app.db.ESQUEMA)
    assert {"desglose_iva"} <= {r[1] for r in c.execute("PRAGMA table_info(documentos)")}
    assert {"re_tasas", "ivas", "logo"} <= {r[1] for r in c.execute("PRAGMA table_info(empresas)")}
    for t in ("ajustes", "correo_config", "envios"):
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone()
    # 3) los datos siguen intactos y se calculan igual
    d = repo.doc(c, 1)
    assert str(repo.totales_cabecera(d)["total"]) == "176.00" and d["desglose_iva"] is None
    # 4) y se puede seguir trabajando: editar la factura antigua y añadir un 7,5 %
    _, ls, _ = repo.documento(c, 1)
    with c:
        repo.guardar_documento(c, 1, "F", repo.datos_de(d), ls + [L("C", 1, 100, "7,5")], did=1)
    assert repo.doc(c, 1)["total"] == "283.50"
    # 5) abrir otra vez la misma versión no hace más copias
    importlib.reload(app.db)
    app.db.connect()
    assert len(list((entorno / "copias-automaticas").glob("*.zip"))) == 1

def test_actualizacion_futura_hace_copia(entorno, monkeypatch):
    """Simula una versión futura: la base dejada por la actual se copia antes de migrar y queda anotada la versión anterior."""
    import app, app.db
    actual = app.__version__
    c = app.db.connect()
    with c:
        c.execute("INSERT INTO empresas(id,codigo,nombre,nif) VALUES(1,'00001','X','B00000000')")
    monkeypatch.setattr(app, "__version__", "9.9.9")
    importlib.reload(app.db)
    c = app.db.connect()
    assert list((entorno / "copias-automaticas").glob("ContFactu-antes-de-9.9.9-*.zip"))
    assert app.db.ajuste(c, "version") == "9.9.9" and app.db.ajuste(c, "version_anterior") == actual

def test_instalacion_nueva_no_hace_copia(entorno):
    import app.db
    app.db.connect()
    assert not (entorno / "copias-automaticas").exists()

def test_copias_automaticas_se_limitan(con, entorno):
    from app import copias
    for _ in range(copias.CONSERVAR_AUTOMATICAS + 3):
        copias.copia_automatica("prueba")
    assert len(list(copias.carpeta_automaticas().glob("*.zip"))) == copias.CONSERVAR_AUTOMATICAS

# ======================================================================================== 2. correo
class LlaveroMemoria:
    def __init__(self): self.d = {}
    def set_password(self, s, u, p): self.d[(s, u)] = p
    def get_password(self, s, u): return self.d.get((s, u))
    def delete_password(self, s, u): self.d.pop((s, u), None)

class SMTPFalso:
    enviados, logins, instancias = [], [], []
    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port; SMTPFalso.instancias.append(self)
    def starttls(self, context=None): self.tls = True
    def login(self, u, p):
        if p != "secreta":
            import smtplib
            raise smtplib.SMTPAuthenticationError(535, b"no")
        SMTPFalso.logins.append((u, p))
    def noop(self): return (250, b"ok")
    def send_message(self, m): SMTPFalso.enviados.append(m); return {}
    def quit(self): pass

@pytest.fixture()
def smtp(monkeypatch):
    from app import correo
    llavero = LlaveroMemoria()
    monkeypatch.setattr(correo, "_keyring", lambda: llavero)
    import smtplib
    SMTPFalso.enviados, SMTPFalso.logins, SMTPFalso.instancias = [], [], []
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTPFalso)
    monkeypatch.setattr(smtplib, "SMTP", SMTPFalso)
    return llavero

CONF = {"servidor": "smtp.example.com", "seguridad": "ssl", "puerto": "465", "usuario": "facturas@example.com",
        "remitente": "facturas@example.com", "nombre_remitente": "Empresa de Prueba", "copia": "",
        "asunto": "Factura {numero} de {empresa}", "cuerpo": "Hola {cliente}:\nAdjunto {el_documento} {numero} por {total} €."}

def test_config_correo_contrasena_fuera_de_la_base(web, con, smtp):
    r = web.post("/e/1/correo", data={**CONF, "contrasena": "secreta"}, follow_redirects=False)
    assert r.status_code == 303
    fila = dict(con.execute("SELECT * FROM correo_config WHERE empresa_id=1").fetchone())
    assert "secreta" not in json.dumps(fila) and smtp.d == {("ContFactu-SMTP", "empresa-1"): "secreta"}
    h = web.get("/e/1/correo").text
    assert "secreta" not in h and "guardada" in h
    # dejar la contraseña en blanco la conserva; marcar «borrar» la quita
    web.post("/e/1/correo", data={**CONF, "contrasena": ""})
    assert smtp.d
    web.post("/e/1/correo", data={**CONF, "borrar_contrasena": "1"})
    assert not smtp.d

def test_config_correo_valida(web, con, smtp):
    r = web.post("/e/1/correo", data={**CONF, "asunto": "Factura {numerito}"})
    assert r.status_code == 400 and "Marcador desconocido" in r.text
    r = web.post("/e/1/correo", data={**CONF, "remitente": "no-es-correo"})
    assert r.status_code == 400 and "no parece un correo" in r.text

def test_probar_conexion(web, con, smtp):
    r = web.post("/e/1/correo", data={**CONF, "contrasena": "secreta", "accion": "probar"})
    assert "Conexión correcta" in r.text and SMTPFalso.logins == [("facturas@example.com", "secreta")]
    assert SMTPFalso.enviados == []                       # probar no envía nada
    r = web.post("/e/1/correo", data={**CONF, "contrasena": "mala", "accion": "probar"})
    assert "rechazado el usuario o la contraseña" in r.text
    r = web.post("/e/1/correo", data={**CONF, "seguridad": "starttls", "puerto": "587", "contrasena": "secreta", "accion": "probar"})
    assert "Conexión correcta" in r.text and SMTPFalso.instancias[-1].port == 587 and SMTPFalso.instancias[-1].tls

def test_enviar_factura_con_vista_previa(web, con, smtp):
    web.post("/e/1/correo", data={**CONF, "contrasena": "secreta"})
    did = nueva(con, [L("Trabajo", 1, 100, "7,5")])
    h = web.get(f"/d/{did}/enviar").text
    assert SMTPFalso.enviados == []                       # la vista previa no envía
    assert 'value="cliente@example.com"' in h             # correo de la ficha del cliente
    assert "Factura 260001 de Empresa de Prueba SL" in h and "Adjunto la factura 260001 por 107,50 €" in h
    r = web.post(f"/d/{did}/enviar", data={"para": "cliente@example.com", "asunto": "x", "cuerpo": "y"})
    assert r.status_code == 400 and SMTPFalso.enviados == []          # sin el clic explícito no se envía
    r = web.post(f"/d/{did}/enviar", data={"para": "cliente@example.com", "copia": "yo@example.com", "asunto": "Factura 260001",
                                           "cuerpo": "Texto revisado", "confirmar": "1"}, follow_redirects=False)
    assert r.status_code == 303 and len(SMTPFalso.enviados) == 1
    m = SMTPFalso.enviados[0]
    assert m["To"] == "cliente@example.com" and m["Cc"] == "yo@example.com" and m["Subject"] == "Factura 260001"
    adj = [p for p in m.iter_attachments()]
    assert len(adj) == 1 and adj[0].get_filename() == "factura_260001.pdf" and adj[0].get_content()[:4] == b"%PDF"
    assert "Texto revisado" in m.get_body(("plain",)).get_content()
    h = web.get(f"/d/{did}").text
    assert "Correos enviados" in h and "enviado" in h

def test_enviar_error_queda_registrado(web, con, smtp):
    web.post("/e/1/correo", data={**CONF, "contrasena": "mala"})
    did = nueva(con, [L("Trabajo", 1, 100)])
    r = web.post(f"/d/{did}/enviar", data={"para": "cliente@example.com", "asunto": "a", "cuerpo": "b", "confirmar": "1"})
    assert r.status_code == 400 and "No se ha enviado" in r.text
    from app import correo
    e = correo.envios(con, did)
    assert e[0]["resultado"] == "error" and "contraseña" in e[0]["error"]
    r = web.post(f"/d/{did}/enviar", data={"para": "esto no", "asunto": "a", "cuerpo": "b", "confirmar": "1"})
    assert r.status_code == 400 and "no parece un correo" in r.text

def test_enviar_sin_configurar(web, con, smtp):
    did = nueva(con, [L("Trabajo", 1, 100)])
    h = web.get(f"/d/{did}/enviar").text
    assert "Falta configurar el correo" in h

def test_plantillas():
    from app import correo
    assert correo.rellenar("{numero} {raro} {total}", {"numero": "1", "total": "2,00"}) == "1 {raro} 2,00"
    assert correo.lista_correos("a@b.es; c@d.com,") == ["a@b.es", "c@d.com"]

# ======================================================================================== 3. Excel
def _wb(data):
    from openpyxl import load_workbook
    return load_workbook(io.BytesIO(data))

def test_excel_libros_formato_aeat(con):
    from app import excel
    nueva(con, [L("A", 1, 100, "21"), L("B", 1, 100, "7,5")], retencion="15")
    nueva(con, [L("Gasto", 1, 40, "21")], tipo="G", num_factura_proveedor="P-77")
    wb = _wb(excel.libros_iva(con, 1, "2026", "1"))
    ws = wb["Emitidas"]
    cab = [c.value for c in ws[2]]
    col = lambda n: cab.index(n) + 1
    assert ws.cell(3, col("Ejercicio")).value == 2026 and ws.cell(3, col("Periodo")).value == "1T"
    assert ws.cell(3, col("Tipo de IVA")).value == 21 and ws.cell(4, col("Tipo de IVA")).value == 7.5
    assert ws.cell(3, col("Total factura")).value == 198.5 and ws.cell(4, col("Total factura")).value is None
    assert ws.cell(3, col("Importe retenido IRPF")).value == 30 and ws.cell(3, col("Tipo retención IRPF")).value == 15
    assert ws.cell(3, col("Base imponible")).number_format.startswith("#,##0.00")
    tot = [r for r in ws.iter_rows() if r[0].value == "TOTALES"][0]
    assert tot[col("Base imponible") - 1].value == 200 and tot[col("Cuota IVA repercutida") - 1].value == 28.5
    assert ws.freeze_panes == "A3" and ws.auto_filter.ref.startswith("A2:")
    rc = wb["Recibidas"]
    cabr = [c.value for c in rc[2]]
    assert rc.cell(3, cabr.index("Nº factura del proveedor") + 1).value == "P-77"
    assert rc.cell(3, cabr.index("Cuota IVA soportada") + 1).value == 8.4

def test_excel_listados(web, con):
    from app import excel
    nueva(con, [L("A", 1, 100, "21")])
    nueva(con, [L("B", 1, 50, "10")], fecha="2026-04-01")
    ws = _wb(excel.documentos(con, 1, "F", "2026")).active
    cab = [c.value for c in ws[2]]
    assert cab[:3] == ["Fecha", "Número", "Cliente"] and ws.cell(3, 1).number_format == "DD/MM/YYYY"
    assert isinstance(ws.cell(3, 1).value, datetime.datetime)
    tot = [r for r in ws.iter_rows() if r[0].value == "TOTALES"][0]
    assert tot[cab.index("Total")].value == 176
    ws = _wb(excel.terceros(con, 1, "clientes")).active
    assert ws.cell(3, 1).value == "C1" and "cliente@example.com" in [c.value for c in ws[3]]
    for url in ("/e/1/documentos.xlsx?tipo=F&anio=2026", "/e/1/clientes.xlsx", "/e/1/proveedores.xlsx", "/e/1/pendientes.xlsx"):
        r = web.get(url)
        assert r.status_code == 200 and r.content[:2] == b"PK" and "attachment" in r.headers["content-disposition"], url
    assert web.get("/e/1/otra.xlsx").status_code == 404

def test_excel_cobros_pendientes(con):
    from app import excel
    nueva(con, [L("A", 1, 100, "21")], fecha="2026-01-10")
    ws = _wb(excel.pendientes(con, 1)).active
    cab = [c.value for c in ws[2]]
    assert ws.cell(3, cab.index("Importe pendiente") + 1).value == 121
    tot = [r for r in ws.iter_rows() if r[0].value == "TOTALES"][0]
    assert tot[cab.index("Importe pendiente")].value == 121 and tot[cab.index("Total documento")].value is None

# ======================================================================================== 4. avisos de cobro
def test_alertas_cobro(con):
    from app import repo
    hoy = datetime.date(2026, 6, 15)
    nueva(con, [L("Vencida", 1, 100)], fecha="2026-05-01")          # vence el mismo día (sin plazos de pago)
    nueva(con, [L("Próxima", 1, 10)], fecha="2026-06-15")
    with con:
        did = nueva(con, [L("Lejana", 1, 10)], fecha="2026-06-15")
        con.execute("UPDATE plazos SET fecha='2026-07-30' WHERE documento_id=?", (did,))
    a = repo.alertas_cobro(con, 1, 7, hoy.isoformat())
    assert [x["importe"] for x in a["vencidos"]] == [D("121.00")] and a["importe_vencido"] == D("121.00")
    assert len(a["proximos"]) == 1 and a["importe_proximo"] == D("12.10")
    # cobrado del todo: deja de avisar
    with con:
        repo.registrar_cobro(con, a["vencidos"][0]["documento_id"], "121.00", "2026-06-15", "", "", None)
    assert not repo.alertas_cobro(con, 1, 7, hoy.isoformat())["vencidos"]

def test_aviso_cobros_en_pantalla_y_ocultar(web, con):
    nueva(con, [L("Vencida", 1, 100)], fecha="2026-01-02")
    h = web.get("/e/1/documentos?tipo=F").text
    assert "1 cobro vencido" in h and 'href="/e/1/pendientes"' in h and "Ocultar" in h
    assert web.post("/e/1/alertas/ocultar", follow_redirects=False).status_code == 303
    assert "cobro vencido" not in web.get("/e/1/documentos?tipo=F").text
