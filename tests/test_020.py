"""0.2.0: acceso opcional desde el móvil. Todo con datos sintéticos.

Con la opción desactivada (el valor de origen) no se abre ningún puerto nuevo.
La API no ofrece la base ni las copias. El token solo se guarda como hash.
"""
import importlib, os, re, socket, sqlite3, ssl, zipfile
from pathlib import Path
import pytest

def _puerto_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p

@pytest.fixture(autouse=True)
def _movil_solo_en_este_equipo(monkeypatch):
    """Ninguna prueba abre el puerto en todas las redes: en el PC de compilación eso dispara el cortafuegos."""
    monkeypatch.setenv("CONTFACTU_MOVIL_HOST", "127.0.0.1")

@pytest.fixture()
def entorno(tmp_path, monkeypatch):
    datos = tmp_path / "datos"
    monkeypatch.setenv("CONTFACTU_DATA", str(datos))
    monkeypatch.delenv("CONTFACTU_DB", raising=False)
    monkeypatch.setenv("CONTFACTU_MOVIL_PUERTO", str(_puerto_libre()))
    import app.db
    importlib.reload(app.db)
    yield datos
    from app import movil
    movil.parar()

@pytest.fixture()
def con(entorno):
    import app.db
    c = app.db.connect()
    with c:
        c.execute("INSERT INTO empresas(id,codigo,nombre,nif,direccion,ciudad,ivas) VALUES(1,'99999','Empresa de Prueba SL','B00000000',"
                  "'C/ Falsa 1','Madrid','21,10,4,0')")
        c.execute("INSERT INTO empresas(id,codigo,nombre,nif) VALUES(2,'99998','Otra Empresa SL','B00000001')")
        c.execute("INSERT INTO clientes(empresa_id,codigo,nombre,nombre_f,nif,email,ciudad) VALUES(1,'C1','Cliente Uno','Cliente Uno SL',"
                  "'12345678Z','cliente@example.com','Madrid')")
        c.execute("INSERT INTO proveedores(empresa_id,codigo,nombre,nif) VALUES(1,'P1','PROVEEDOR-SECRETO-XYZ','B99999999')")
    return c

@pytest.fixture()
def web(con):
    import app.main
    importlib.reload(app.main)
    from fastapi.testclient import TestClient
    return TestClient(app.main.app)

@pytest.fixture()
def api(con):
    from fastapi.testclient import TestClient
    from app.api_movil import aplicacion
    return TestClient(aplicacion)

def _permitir(con):
    from app.db import poner_ajuste
    with con:
        poner_ajuste(con, "movil_activo", "1")

def _rutas(aplicacion):
    encontradas = set()
    for r in aplicacion.routes:
        path = getattr(r, "path", None)
        for m in (getattr(r, "methods", None) or ()):
            if m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                encontradas.add((m, path))
    return encontradas

def _escucha(port):
    """True si algo acepta TCP en 127.0.0.1:puerto. Vale en Windows y en Linux."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()

# -------------------------------------------------------------------------------- valores de origen y red
def test_desactivado_por_defecto_y_solo_local(con, web, entorno):
    import app.__main__ as M
    from app import movil
    from app.main import app as aplicacion_local
    assert not movil.activado(con)
    assert movil.sincronizar() is False
    assert not movil.en_marcha() and movil.enlace() is None
    assert M.HOST_INTERFAZ == "127.0.0.1"
    assert M.config_interfaz(aplicacion_local, 9).host == "127.0.0.1"
    assert movil.HOST_MOVIL == "0.0.0.0"
    assert movil.host_escucha() == "127.0.0.1"
    assert _escucha(movil.puerto()) is False
    h = web.get("/ajustes").text
    assert "Permitir acceso desde el móvil" in h and "Ajustes" in h
    assert "checked" not in h
    assert "Código de respaldo" not in h and "sha256:" not in h and "Emparejar un dispositivo" not in h
    assert not (entorno / "movil").exists()
    assert web.get("/api/v1/salud").status_code == 404
    assert web.get("/api/v1/empresas").status_code == 404
    assert web.post("/api/v1/emparejar", json={"codigo": "AAAA-AAAA", "nombre": "x"}).status_code == 404

def test_la_interfaz_sigue_en_local_aunque_el_movil_este_activo(con):
    import app.__main__ as M
    from app import movil
    from app.main import app as aplicacion_local
    _permitir(con)
    assert M.config_interfaz(aplicacion_local, 9).host == "127.0.0.1"
    port = None
    movil.activar(con)
    try:
        host, port = movil.enlace()
        assert host == "127.0.0.1" and _escucha(port) is True
        assert M.config_interfaz(aplicacion_local, 9).host == "127.0.0.1"
    finally:
        movil.parar()
        assert not movil.en_marcha() and (port is None or not _escucha(port))

def test_activado_escucha_en_todas_las_interfaces(monkeypatch):
    """Comprueba la dirección de producción sin abrir un socket en todas las interfaces."""
    from app import movil
    assert movil.host_escucha() == "127.0.0.1"
    monkeypatch.delenv("CONTFACTU_MOVIL_HOST", raising=False)
    assert movil.host_escucha() == movil.HOST_MOVIL == "0.0.0.0"
    assert not movil.en_marcha()

def test_clasifica_wifi_wireguard_y_tailscale():
    from app import movil
    dirs = movil.clasificar([("eth0", "192.168.1.20"), ("wg0", "10.8.0.2"), ("tailscale0", "100.64.1.5"),
                             ("lo", "127.0.0.1"), ("docker0", "172.17.0.1"), ("enp0s3", "169.254.1.1")])
    assert [d["ip"] for d in dirs] == ["192.168.1.20", "10.8.0.2", "100.64.1.5"]
    assert [d["tipo"] for d in dirs] == ["local", "wireguard", "tailscale"]
    for d in movil.direcciones():
        assert not d["ip"].startswith("127.")

def test_ajustes_solo_desde_este_equipo(con, web):
    from fastapi.testclient import TestClient
    import app.main
    remoto = TestClient(app.main.app, client=("10.1.2.3", 9))
    assert remoto.get("/ajustes").status_code == 403
    assert remoto.post("/ajustes", data={"permitir": "1"}).status_code == 403
    assert web.post("/ajustes", data={"permitir": "1"}, headers={"Origin": "http://evil.example"},
                    follow_redirects=False).status_code == 403
    from app import movil
    assert not movil.activado(con) and not movil.en_marcha()

# -------------------------------------------------------------------------------- emparejamiento y tokens
def test_sin_token_o_token_revocado(con, api):
    from app import movil
    _permitir(con)
    assert api.get("/api/v1/empresas").status_code == 401
    assert api.get("/api/v1/empresas").json()["error"] == "Acceso no autorizado."
    codigo = movil.nuevo_codigo(con)["codigo"]
    assert api.get(f"/api/v1/empresas?access_token=no-vale").status_code == 401
    r = api.post("/api/v1/emparejar", json={"codigo": codigo, "nombre": "Pixel de prueba"})
    assert r.status_code == 200
    token = r.json()["token"]
    guardado = con.execute("SELECT token_hash FROM dispositivos_movil").fetchone()[0]
    assert guardado != token and set(guardado) <= set("0123456789abcdef") and len(guardado) == 64
    assert codigo not in "".join((v or "") for (v,) in con.execute("SELECT valor FROM ajustes"))
    auth = {"Authorization": f"Bearer {token}"}
    assert api.get("/api/v1/empresas", headers=auth).status_code == 200
    movil.revocar(con, r.json()["dispositivo_id"])
    otra = api.get("/api/v1/empresas", headers=auth)
    assert otra.status_code == 401 and otra.json()["error"] == "Acceso no autorizado."
    assert api.get("/api/v1/empresas", headers={"Authorization": "Bearer " + "a" * 40}).status_code == 401

def test_token_no_vale_si_se_desactiva(con, api):
    from app import movil
    from app.db import poner_ajuste
    _permitir(con)
    token = movil.emparejar(con, movil.nuevo_codigo(con)["codigo"], "Uno")["token"]
    with con:
        poner_ajuste(con, "movil_activo", "0")
    assert api.get("/api/v1/empresas", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert api.get("/api/v1/salud").status_code == 404

def test_limite_de_intentos(con, api):
    from app import movil
    _permitir(con)
    assert movil.MAX_FALLOS == 5 and movil.BLOQUEO_SEGUNDOS == 15 * 60
    bueno = movil.nuevo_codigo(con)["codigo"]
    for _ in range(4):
        r = api.post("/api/v1/emparejar", json={"codigo": "ZZZZ-ZZZZ", "nombre": "x"})
        assert r.status_code == 401 and "no es válido" in r.json()["error"]
    r = api.post("/api/v1/emparejar", json={"codigo": "ZZZZ-ZZZZ", "nombre": "x"})
    assert r.status_code == 429 and r.json()["reintentar_en"] >= 60
    assert api.post("/api/v1/emparejar", json={"codigo": bueno, "nombre": "x"}).status_code == 429
    with pytest.raises(movil.ErrorMovil):
        movil.nuevo_codigo(con)
    from fastapi.testclient import TestClient
    import app.main
    pag = TestClient(app.main.app).get("/ajustes")
    assert pag.status_code == 200 and "Desbloquear emparejamiento" in pag.text
    assert "Emparejar un dispositivo</button>" not in pag.text
    movil.desbloquear(con)
    ok = api.post("/api/v1/emparejar", json={"codigo": bueno.lower(), "nombre": "Tras el bloqueo"})
    assert ok.status_code == 200
    assert api.post("/api/v1/emparejar", json={"codigo": bueno, "nombre": "otra vez"}).status_code == 401

def test_qr_lleva_codigo_y_huella(con, web):
    from app import movil
    r = web.post("/ajustes", data={"permitir": "1"}, follow_redirects=True)
    assert r.status_code == 200 and "checked" in r.text and "Emparejar un dispositivo" in r.text
    assert movil.en_marcha()
    pag = web.post("/ajustes/emparejar")
    assert pag.status_code == 200 and "Código de respaldo" in pag.text and 'id="qr-emparejar"' in pag.text
    codigo = re.search(r'id="codigo-respaldo"[^>]*>([^<]+)', pag.text).group(1)
    huella = re.search(r'id="huella-certificado"[^>]*>([^<]+)', pag.text).group(1)
    assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", codigo)
    assert huella == movil.huella() and huella.startswith("sha256:") and len(huella) == 7 + 64
    payload = movil.payload_qr(codigo, [d["ip"] for d in movil.direcciones()], movil.puerto(), huella)
    texto = movil.payload_json(payload)
    assert codigo in texto and huella in texto and '"v":1' in texto and '"app":"ContFactu"' in texto
    svg = movil.qr_svg(texto)
    assert svg and svg.count("<rect") > 20
    assert codigo.encode() not in (Path(os.environ["CONTFACTU_DATA"]) / "contfactu.db").read_bytes()

# -------------------------------------------------------------------------------- API de facturas
def _auth(api, con):
    from app import movil
    _permitir(con)
    token = movil.emparejar(con, movil.nuevo_codigo(con)["codigo"], "App de prueba")["token"]
    return {"Authorization": f"Bearer {token}"}

def test_facturas_clientes_busqueda_y_pdf_sin_volcado(con, api):
    from app import repo
    auth = _auth(api, con)
    with con:
        repo.guardar_documento(con, 1, "A", {"fecha": "2026-11-01", "nombre_f": "ALBARAN-NO-EN-API"},
                               [{"concepto": "No", "cantidad": "1", "precio": "5", "iva": "21"}])
    assert api.get("/api/v1/salud", headers=auth).json()["api"] == 1
    assert "Empresa de Prueba" not in api.get("/api/v1/salud", headers=auth).text
    empresas = api.get("/api/v1/empresas", headers=auth).json()["empresas"]
    assert {e["id"] for e in empresas} == {1, 2}
    assert "PROVEEDOR-SECRETO-XYZ" not in api.get("/api/v1/empresas", headers=auth).text
    body = {"fecha": "2026-11-10", "nombre_f": "Cliente Uno SL", "nif": "12345678Z", "cliente_codigo": "C1",
            "lineas": [{"concepto": "Tornillos", "cantidad": "1", "precio": "100", "iva": "21"},
                       {"concepto": "Especial", "cantidad": 1, "precio": "100,00", "iva": "7,5"}]}
    r = api.post("/api/v1/empresas/1/facturas", json=body, headers=auth)
    assert r.status_code == 201, r.text
    factura = r.json()
    assert factura["total"] == "228.50" and factura["numero"].startswith("26")
    assert any(l["iva"] in ("7.5", "7.50") for l in factura["lineas"])
    assert repo.doc(con, factura["id"])["total"] == "228.50"
    body["lineas"][1]["precio"] = "200"
    edit = api.put(f"/api/v1/empresas/1/facturas/{factura['id']}", json=body, headers=auth)
    assert edit.status_code == 200 and edit.json()["total"] == "336.00"
    assert edit.json()["numero"] == factura["numero"]
    pdf = api.get(f"/api/v1/empresas/1/facturas/{factura['id']}/pdf", headers=auth)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and pdf.headers["content-type"].startswith("application/pdf")
    assert api.get(f"/api/v1/empresas/2/facturas/{factura['id']}", headers=auth).status_code == 404
    albaran = con.execute("SELECT id FROM documentos WHERE tipo='A'").fetchone()[0]
    assert api.get(f"/api/v1/empresas/1/facturas/{albaran}/pdf", headers=auth).status_code == 404
    mala = api.post("/api/v1/empresas/1/facturas", headers=auth, json={
        "nombre_f": "Cliente Uno SL", "fecha": "2026-11-10",
        "lineas": [{"concepto": "Mal", "cantidad": "1", "precio": "10", "iva": "150"}]})
    assert mala.status_code == 400 and mala.json()["campo"] == "iva" and mala.json()["indice"] == 0
    assert "entre 0 % y 100 %" in mala.json()["error"]
    dto = api.post("/api/v1/empresas/1/facturas", headers=auth, json={
        "nombre_f": "Cliente Uno SL", "fecha": "2026-11-10", "descuento": "101",
        "lineas": [{"concepto": "Mal", "cantidad": "1", "precio": "10", "iva": "21", "descuento": "10"}]})
    assert dto.status_code == 400 and dto.json()["campo"] == "descuento" and "indice" not in dto.json()
    assert "El descuento debe estar entre 0 % y 100 %" in dto.json()["error"]
    linea_dto = api.put(f"/api/v1/empresas/1/facturas/{factura['id']}", headers=auth, json={
        "nombre_f": "Cliente Uno SL", "fecha": "2026-11-10",
        "lineas": [{"concepto": "Mal", "cantidad": "1", "precio": "10", "iva": "7,555", "descuento": "-1"}]})
    assert linea_dto.status_code == 400 and linea_dto.json()["campo"] == "descuento" and linea_dto.json()["indice"] == 0
    fina = api.post("/api/v1/empresas/1/facturas", headers=auth, json={
        "nombre_f": "Cliente Uno SL", "fecha": "2026-11-10",
        "lineas": [{"concepto": "Fino", "cantidad": "1", "precio": "100", "iva": "7,555"}]})
    assert fina.status_code == 201 and fina.json()["lineas"][0]["iva"] == "7.555"
    clientes = api.get("/api/v1/empresas/1/clientes?q=Uno", headers=auth).json()["clientes"]
    assert clientes and clientes[0]["nif"] == "12345678Z"
    bus = api.get("/api/v1/empresas/1/buscar?q=Cliente", headers=auth).json()
    assert bus["total"] >= 1 and any(c["nif"] == "12345678Z" for c in bus["clientes"])
    proveedor = api.get("/api/v1/empresas/1/buscar?q=PROVEEDOR-SECRETO-XYZ", headers=auth).json()
    assert proveedor["clientes"] == [] and proveedor["facturas"] == [] and proveedor["total"] == 0
    secreto = api.get("/api/v1/empresas/1/buscar?q=ALBARAN-NO-EN-API", headers=auth).json()
    assert secreto["facturas"] == [] and secreto["total"] == 0

def test_la_api_no_descarga_la_base_ni_copias(con, api):
    from app.api_movil import RUTAS, aplicacion
    _permitir(con)
    assert _rutas(aplicacion) == RUTAS
    assert not any(m == "DELETE" for m, _p in _rutas(aplicacion))
    for ruta in ("/copias", "/api/v1/backup", "/api/v1/sqlite", "/docs", "/openapi.json", "/api/v1/empresas/1/export"):
        assert api.get(ruta).status_code == 404, ruta

def test_clave_y_token_no_van_en_la_copia(con, entorno, tmp_path):
    from app import copias, movil
    _permitir(con)
    movil.asegurar_certificado()
    clave = entorno / "movil" / "clave.pem"
    assert clave.is_file()
    if os.name == "posix":
        # En Windows os.chmod no aplica el modo Unix: st_mode queda 0o666. La carpeta del usuario protege el archivo.
        assert (clave.stat().st_mode & 0o777) == 0o600
    assert b"PRIVATE KEY" not in (entorno / "contfactu.db").read_bytes()
    token = movil.emparejar(con, movil.nuevo_codigo(con)["codigo"], "Copia")["token"]
    z = copias.crear_copia(con, str(tmp_path / "copias"))
    with zipfile.ZipFile(z) as zipf:
        assert all(not n.endswith(".pem") and "clave" not in n for n in zipf.namelist())
        assert b"PRIVATE KEY" not in zipf.read("contfactu.db")
        assert token.encode() not in zipf.read("contfactu.db")

# -------------------------------------------------------------------------------- TLS
def test_tls_huella_y_rechazo_sin_token(con):
    import httpx
    from app import movil
    movil.activar(con)
    try:
        _host, port = movil.enlace()
        cert = entorno_cert = movil._rutas_cert()[0]
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
            with ctx.wrap_socket(raw, server_hostname="contfactu.local") as ss:
                der = ss.getpeercert(binary_form=True)
                assert ss.version() in ("TLSv1.2", "TLSv1.3")
        assert movil.huella_de_der(der) == movil.huella()
        assert not movil.huellas_iguales(movil.huella(), "sha256:" + "ab" * 32)
        confiado = ssl.create_default_context(cafile=str(entorno_cert))
        confiado.check_hostname = False
        with httpx.Client(verify=confiado, timeout=5) as cliente:
            salud = cliente.get(f"https://127.0.0.1:{port}/api/v1/salud")
            assert salud.status_code == 200 and salud.json()["nombre"] == "ContFactu"
            assert cliente.get(f"https://127.0.0.1:{port}/api/v1/empresas").status_code == 401
            codigo = movil.nuevo_codigo(con)["codigo"]
            alta = cliente.post(f"https://127.0.0.1:{port}/api/v1/emparejar",
                                json={"codigo": codigo, "nombre": "Cliente TLS"})
            assert alta.status_code == 200
            token = alta.json()["token"]
            facturas = cliente.get(f"https://127.0.0.1:{port}/api/v1/empresas/1/facturas?anio=todos",
                                   headers={"Authorization": f"Bearer {token}"})
            assert facturas.status_code == 200 and "facturas" in facturas.json()
            assert cliente.get(f"https://127.0.0.1:{port}/copias").status_code == 404
        with pytest.raises(Exception):
            httpx.get(f"https://127.0.0.1:{port}/api/v1/salud", timeout=5, verify=True)
        with pytest.raises(Exception):
            httpx.get(f"http://127.0.0.1:{port}/api/v1/salud", timeout=2)
        viejo = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        viejo.check_hostname = False
        viejo.verify_mode = ssl.CERT_NONE
        try:
            viejo.maximum_version = ssl.TLSVersion.TLSv1_1
            viejo.minimum_version = ssl.TLSVersion.TLSv1
        except ValueError:
            viejo = None
        if viejo is not None:
            with pytest.raises(ssl.SSLError):
                with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                    with viejo.wrap_socket(raw, server_hostname="contfactu.local"):
                        pass
    finally:
        movil.parar()

# -------------------------------------------------------------------------------- actualización desde 0.1.0
def test_actualizacion_desde_010_conserva_datos_y_sigue_apagado(entorno):
    import app.db
    from app import movil, repo
    c = app.db.connect()
    with c:
        c.execute("INSERT INTO empresas(id,codigo,nombre,nif) VALUES(1,'00001','Antigua SL','B00000000')")
        did = repo.guardar_documento(c, 1, "F", {"fecha": "2026-04-01", "nombre_f": "Cliente Antiguo", "nif": "12345678Z"},
                                     [{"concepto": "A", "cantidad": "1", "precio": "100", "iva": "21"}])
        app.db.poner_ajuste(c, "version", "0.1.0")
        app.db.poner_ajuste(c, "esquema", "4")
        c.execute("DROP TABLE dispositivos_movil")
    assert repo.doc(c, did)["total"] == "121.00"
    c.close()
    app.db.olvidar_preparacion()
    importlib.reload(app.db)
    c = app.db.connect()
    autos = list((entorno / "copias-automaticas").glob("ContFactu-antes-de-0.2.0-*.zip"))
    assert len(autos) == 1
    with zipfile.ZipFile(autos[0]) as z:
        previa = entorno / "previa.db"
        previa.write_bytes(z.read("contfactu.db"))
    vieja = sqlite3.connect(previa)
    assert vieja.execute("SELECT valor FROM ajustes WHERE clave='version'").fetchone()[0] == "0.1.0"
    assert not vieja.execute("SELECT 1 FROM sqlite_master WHERE name='dispositivos_movil'").fetchone()
    assert vieja.execute("SELECT total FROM documentos WHERE id=?", (did,)).fetchone()[0] == "121.00"
    vieja.close()
    assert app.db.version_datos(entorno / "contfactu.db") == ("0.2.0", app.db.ESQUEMA)
    assert app.db.ajuste(c, "version_anterior") == "0.1.0"
    assert c.execute("SELECT nombre FROM empresas WHERE id=1").fetchone()[0] == "Antigua SL"
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='dispositivos_movil'").fetchone()
    assert not movil.activado(c)
    assert movil.sincronizar() is False and not movil.en_marcha()
    d = repo.doc(c, did)
    _d, ls, _p = repo.documento(c, did)
    with c:
        repo.guardar_documento(c, 1, "F", repo.datos_de(d), ls + [{"concepto": "B", "cantidad": "1", "precio": "100", "iva": "7,5"}], did=did)
    assert repo.doc(c, did)["total"] == "228.50"
    importlib.reload(app.db)
    app.db.connect().close()
    assert len(list((entorno / "copias-automaticas").glob("ContFactu-antes-de-0.2.0-*.zip"))) == 1

def test_puente_no_expone_el_movil():
    from app.ventana import Puente
    p = Puente("http://127.0.0.1:9")
    publicos = {n for n in dir(p) if not n.startswith("_")}
    assert publicos == {"abrir", "guardar", "elegir_carpeta", "elegir_zip", "abrir_externo"}
    for n in publicos:
        assert not isinstance(getattr(p, n), (socket.socket, ssl.SSLSocket))

def test_revocar_desde_ajustes(con, web, api):
    from app import movil
    web.post("/ajustes", data={"permitir": "1"}, follow_redirects=True)
    pag = web.post("/ajustes/emparejar")
    codigo = re.search(r'id="codigo-respaldo"[^>]*>([^<]+)', pag.text).group(1)
    alta = api.post("/api/v1/emparejar", json={"codigo": codigo, "nombre": "Para revocar"})
    token = alta.json()["token"]
    assert "Para revocar" in web.get("/ajustes").text
    assert web.post("/ajustes/revocar", data={"id": str(alta.json()["dispositivo_id"])}, follow_redirects=True).status_code == 200
    assert "Para revocar" not in web.get("/ajustes").text
    assert "Ningún dispositivo emparejado." in web.get("/ajustes").text
    assert api.get("/api/v1/empresas", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    movil.parar()

def test_desactivar_cierra_el_puerto(con, web):
    from app import movil
    web.post("/ajustes", data={"permitir": "1"}, follow_redirects=True)
    assert movil.en_marcha()
    r = web.post("/ajustes", data={}, follow_redirects=True)
    assert "desactivado" in r.text.lower() or "Desactivado" in r.text
    assert not movil.activado(con) and not movil.en_marcha()
    assert "checked" not in web.get("/ajustes").text
