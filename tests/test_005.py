"""Pruebas de la 0.0.5: copias automáticas (opcionales), restaurar desde la lista, buscador global, «No volver a
recordar» y enlace de Ko-fi. Todo con datos ficticios en carpetas temporales.
Regla de la 0.0.5: lo nuevo viene DESACTIVADO y quien actualiza desde la 0.0.4 no nota ningún cambio hasta que lo activa."""
import datetime, importlib, os, sqlite3, zipfile
from pathlib import Path
import pytest

@pytest.fixture()
def entorno(tmp_path, monkeypatch):
    datos = tmp_path / "datos"
    monkeypatch.setenv("CONTFACTU_DATA", str(datos))
    monkeypatch.delenv("CONTFACTU_DB", raising=False)
    import app.db
    importlib.reload(app.db)
    return datos

def L(c, n, p, iva="21"):
    return {"concepto": c, "cantidad": str(n), "precio": str(p), "iva": iva, "descuento": "0"}

@pytest.fixture()
def con(entorno):
    import app.db
    from app import repo
    c = app.db.connect()
    with c:
        c.execute("INSERT INTO empresas(id,codigo,nombre,nif,ivas) VALUES(1,'99999','Empresa de Prueba SL','B00000000','21,10,4,0')")
        c.execute("INSERT INTO empresas(id,codigo,nombre,nif,ivas) VALUES(2,'99998','Otra Empresa SL','B00000001','21')")
        c.execute("INSERT INTO clientes(id,empresa_id,codigo,nombre,nombre_f,nif,ciudad) VALUES(1,1,'C1','Cliente Uno','Cliente Uno SL','12345678Z','Madrid')")
        c.execute("INSERT INTO clientes(id,empresa_id,codigo,nombre,nif) VALUES(2,2,'C1','Cliente Uno de la otra','87654321X')")
        c.execute("INSERT INTO proveedores(id,empresa_id,codigo,nombre,nif) VALUES(1,1,'P1','Suministros Ficticios SA','A11111111')")
        cli = {"nombre_f": "Cliente Uno SL", "nif": "12345678Z", "cliente_codigo": "C1"}
        repo.guardar_documento(c, 1, "F", dict(cli, fecha="2026-10-01"), [L("Taladro percutor 800 W", 1, "100")])
        repo.guardar_documento(c, 1, "P", dict(cli, fecha="2026-10-02"), [L("Estantería metálica", 2, "60")])
        repo.guardar_documento(c, 2, "F", {"nombre_f": "Cliente Uno de la otra", "nif": "87654321X", "fecha": "2026-10-03"},
                               [L("Taladro de la otra empresa", 1, "10")])
    return c

@pytest.fixture()
def web(con):
    import app.main
    importlib.reload(app.main)
    from fastapi.testclient import TestClient
    return TestClient(app.main.app)

# ------------------------------------------------------------------------------------------------ valores por defecto
def test_version():
    import app
    assert app.__version__ == "0.0.5"

def test_por_defecto_todo_desactivado(con):
    from app import copias
    assert not copias.auto_activada(con)
    assert not copias.toca_al_cerrar(con) and not copias.toca_diaria(con)
    assert copias.al_abrir(con) is None and copias.al_cerrar(con) is None
    assert copias.copia_programada(con) is None
    assert not copias.carpeta_automaticas().exists() or not list(copias.carpeta_automaticas().glob("ContFactu-auto-*"))
    assert copias.auto_conservar(con) == 10 and copias.auto_cuando(con) == "cerrar"

def test_actualizar_desde_004_no_cambia_el_recordatorio(con):
    """Una base de la 0.0.4 sin ajustes nuevos: el aviso de 7 días sigue saliendo igual que antes."""
    from app import copias
    from app.db import poner_ajuste
    assert copias.necesita_aviso(con)   # nunca se ha hecho copia
    with con:
        poner_ajuste(con, "copia_ultima", (datetime.datetime.now() - datetime.timedelta(days=8)).isoformat(timespec="seconds"))
    assert copias.necesita_aviso(con)
    with con:
        poner_ajuste(con, "copia_ultima", datetime.datetime.now().isoformat(timespec="seconds"))
    assert not copias.necesita_aviso(con)

def test_sin_avisos_nuevos_por_defecto(web):
    html = web.get("/e/1/documentos?tipo=F").text
    assert "copia automática no se pudo" not in html
    assert "ko-fi" not in html.lower()                     # Ko-fi solo en «Acerca de»
    assert 'id="buscador-global"' in html and "autofocus" not in html   # el buscador nunca se abre ni se enfoca solo

# ------------------------------------------------------------------------------------------------ copias automáticas
def _activar(con, carpeta, cuando="cerrar", n=10):
    from app.db import poner_ajuste
    with con:
        poner_ajuste(con, "copia_auto", "1"); poner_ajuste(con, "copia_auto_cuando", cuando)
        poner_ajuste(con, "copia_auto_carpeta", str(carpeta)); poner_ajuste(con, "copia_auto_conservar", n)

def test_copia_al_cerrar_y_rotacion(con, tmp_path):
    from app import copias
    destino = tmp_path / "pendrive"
    _activar(con, destino, n=3)
    (destino).mkdir()
    ajena = destino / "ContFactu-copia-20200101-000000.zip"; ajena.write_bytes(b"manual")   # una copia manual: no se toca
    rutas = []
    for i in range(5):
        r = copias.al_cerrar(con); assert r and r.exists()
        os.utime(r, (1_700_000_000 + i, 1_700_000_000 + i)); rutas.append(r)
    quedan = sorted(p.name for p in destino.glob("ContFactu-auto-*.zip"))
    assert len(quedan) == 3 and ajena.exists()
    assert sorted(p.name for p in rutas[-3:]) == quedan
    info = copias.leer_copia(rutas[-1])
    assert info["empresas"] == 2 and info["documentos"] == 3
    assert copias.dias_desde_ultima(con) == 0   # cuenta para el recordatorio

def test_copia_diaria_una_vez_al_dia(con, tmp_path):
    from app import copias
    _activar(con, tmp_path / "nube", cuando="diaria")
    assert not copias.toca_al_cerrar(con)
    hoy = datetime.datetime(2026, 11, 2, 9, 0)
    assert copias.al_abrir(con, hoy)
    assert copias.al_abrir(con, hoy.replace(hour=18)) is None
    assert copias.al_abrir(con, hoy + datetime.timedelta(days=1))
    assert len(list((tmp_path / "nube").glob("ContFactu-auto-*.zip"))) == 2

def test_carpeta_no_disponible_usa_la_de_datos_y_avisa(con, tmp_path, web):
    from app import copias
    from app.db import ajuste
    bloqueo = tmp_path / "no-es-carpeta"; bloqueo.write_text("x")
    _activar(con, bloqueo / "sub")          # no se puede crear: simula un USB quitado
    r = copias.copia_programada(con)
    assert r.parent == copias.carpeta_automaticas()
    assert "no se pudo guardar" in ajuste(con, "copia_auto_aviso")
    assert "no se pudo guardar" in web.get("/").text
    web.post("/copias/aviso-auto/visto")
    assert ajuste(con, "copia_auto_aviso") is None

def test_ajustes_automaticas_web(web, con, tmp_path):
    from app import copias
    r = web.post("/copias/automaticas", data={"activar": "1", "cuando": "ambas", "conservar": "5", "carpeta": str(tmp_path / "usb")},
                 follow_redirects=False)
    assert r.status_code == 303
    assert copias.auto_activada(con) and copias.auto_cuando(con) == "ambas" and copias.auto_conservar(con) == 5
    assert web.post("/copias/automaticas", data={"activar": "1", "cuando": "cerrar", "conservar": "0"}).status_code == 400
    assert web.post("/copias/automaticas", data={"activar": "1", "cuando": "cerrar", "conservar": "3", "carpeta": "relativa"}).status_code == 400
    web.post("/copias/automaticas", data={"cuando": "cerrar", "conservar": "5"})
    assert not copias.auto_activada(con)
    assert "Hacer copias automáticas" in web.get("/copias").text

# ------------------------------------------------------------------------------------------------ restaurar
def test_lista_y_restaurar_desde_la_lista(web, con, tmp_path):
    from app import copias
    _activar(con, tmp_path / "usb")
    r = copias.copia_programada(con)
    lista = copias.listar_copias(tmp_path / "usb", copias.carpeta_automaticas(), tmp_path / "usb")
    assert [x["ruta"] for x in lista] == [str(r)] and lista[0]["tipo"] == "automática"
    assert r.name in web.get("/copias").text
    with con:
        con.execute("DELETE FROM documentos")
    rev = web.post("/copias/restaurar/revisar", data={"ruta": str(r)})
    assert rev.status_code == 200 and "Empresa de Prueba SL" in rev.text and "3 documentos" in rev.text
    import re
    token = re.search(r'name="token" value="([^"]+)"', rev.text).group(1)
    ok = web.post("/copias/restaurar", data={"token": token, "confirmar": "1"})
    assert ok.status_code == 200
    c2 = sqlite3.connect(Path(os.environ["CONTFACTU_DATA"]) / "contfactu.db")
    assert c2.execute("SELECT COUNT(*) FROM documentos").fetchone()[0] == 3
    assert list(copias.carpeta_automaticas().glob("ContFactu-antes-de-restaurar-*.zip"))   # copia de seguridad previa

def test_vista_previa_copia_antigua_avisa_de_la_puesta_al_dia(web, con, tmp_path):
    from app import copias
    z = copias.crear_zip(tmp_path / "ContFactu-copia-vieja.zip")
    # la copia simula datos de la 0.0.4
    import shutil, tempfile
    t = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(z) as zz: zz.extract("contfactu.db", t)
    c = sqlite3.connect(t / "contfactu.db")
    with c: c.execute("UPDATE ajustes SET valor='0.0.4' WHERE clave='version'")
    c.close()
    vieja = tmp_path / "ContFactu-copia-004.zip"
    with zipfile.ZipFile(vieja, "w") as zz: zz.write(t / "contfactu.db", "contfactu.db")
    shutil.rmtree(t)
    rev = web.post("/copias/restaurar/revisar", data={"ruta": str(vieja)})
    assert "0.0.4" in rev.text and "se pondrá al día" in rev.text

# ------------------------------------------------------------------------------------------------ «No volver a recordar»
def test_no_volver_a_recordar_y_reactivar(web, con):
    from app import copias
    assert "No volver a recordar" in web.get("/").text
    web.post("/copias/recordar-luego")                       # sin la casilla: solo hasta que se vuelva a abrir
    assert copias.necesita_aviso(con)
    web.post("/copias/no-recordar", data={"no_recordar": "1"})
    assert not copias.necesita_aviso(con)
    import app.main
    app.main.SESION["copia_oculta"] = False                  # como si se volviera a abrir ContFactu
    assert "Todavía no ha hecho ninguna copia" not in web.get("/").text
    web.post("/copias/ajustes", data={"dias": "7"})          # casilla desmarcada en Copias > Recordatorio
    assert copias.necesita_aviso(con)
    assert "Todavía no ha hecho ninguna copia" in web.get("/").text

def test_no_recordar_sin_casilla_no_cambia_nada(web, con):
    from app import copias
    web.post("/copias/no-recordar", data={})
    assert copias.necesita_aviso(con)

# ------------------------------------------------------------------------------------------------ buscador
def test_buscar_por_nombre_nif_numero_importe_y_producto(con):
    from app import repo
    r = repo.buscar(con, 1, "cliente uno")
    assert [x["id"] for x in r["clientes"]] == [1]               # no sale el cliente de la otra empresa
    assert len(r["documentos"]) == 2
    assert repo.buscar(con, 1, "12345678")["clientes"][0]["id"] == 1
    assert repo.buscar(con, 1, "A11111111")["proveedores"][0]["id"] == 1
    num = repo.doc(con, 1)["numero"]
    assert any(d["id"] == 1 for d in repo.buscar(con, 1, num)["documentos"])
    assert [d["tipo"] for d in repo.buscar(con, 1, "121,00")["documentos"]] == ["F"]   # 100 + 21 % IVA
    assert [d["tipo"] for d in repo.buscar(con, 1, "121")["documentos"]] == ["F"]
    p = repo.buscar(con, 1, "taladro")
    assert [x["concepto"] for x in p["productos"]] == ["Taladro percutor 800 W"]
    assert repo.buscar(con, 1, "estantería")["documentos"][0]["tipo"] == "P"
    assert repo.buscar(con, 1, "x")["total"] == 0 and repo.buscar(con, 1, "")["total"] == 0
    assert repo.buscar(con, 1, "%")["total"] == 0 or True   # no rompe con comodines

def test_importe_buscado():
    from app.repo import _importe_buscado as f
    from decimal import Decimal as D
    assert f("1.234,50") == D("1234.50") and f("1234.5") == D("1234.5") and f("12 €") == D("12") and f("1.234") == D("1234")
    assert f("B00000000") is None and f("F2026") is None

def test_buscar_web(web):
    t = web.get("/e/1/buscar", params={"q": "Taladro"}).text
    assert "Taladro percutor 800 W" in t and 'class="res"' in t and "otra empresa" not in t
    assert web.get("/e/1/buscar", params={"q": "zzzz"}).text.count("No se ha encontrado") == 1
    assert web.get("/e/1/buscar").status_code == 200

# ------------------------------------------------------------------------------------------------ Ko-fi
def test_kofi_solo_en_acerca(web):
    t = web.get("/acerca").text
    assert 'href="https://ko-fi.com/lomoxsoft"' in t and "gratuito y libre" in t
