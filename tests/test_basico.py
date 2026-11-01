import os, tempfile, pytest
from pathlib import Path
# Pruebas con una copia REAL de FactuCont 5: solo se ejecutan si se indica su carpeta FC5 en CONTFACTU_FC5
# (empresas 00001 y 00008). Ningún dato real se guarda en el repositorio.
FC5 = Path(os.environ.get("CONTFACTU_FC5") or "/no-existe/FC5")

@pytest.fixture(scope="module")
def con(tmp_path_factory):
    db = tmp_path_factory.mktemp("d") / "t.db"
    os.environ["CONTFACTU_DB"] = str(db)
    import importlib, app.db
    importlib.reload(app.db)
    from app.importer import importar_empresa
    c = app.db.connect(db)
    with c:
        for cod in ("00001", "00008"):
            importar_empresa(c, str(FC5), cod)
    return c

def test_calc_basico():
    from app.calc import bases_desde_lineas, totales_cabecera, fmt_eur
    ls = [{"cantidad": "2", "precio": "10", "descuento": "0", "iva": "21"}, {"cantidad": "1", "precio": "5", "iva": "10"},
          {"concepto": "comentario", "comentario": 1}]
    b = bases_desde_lineas(ls)
    assert {str(k): str(v) for k, v in b.items()} == {"21": "20.00", "10": "5.00"}
    t = totales_cabecera({"base1": "20", "iva1": "21", "base2": "5", "iva2": "10"})
    assert str(t["total"]) == "29.70" and fmt_eur(1234.5, True) == "1.234,50 €"

@pytest.mark.skipif(not FC5.exists(), reason="sin datos FactuCont")
def test_importacion_y_reimportacion(con):
    from app.importer import importar_empresa
    n1 = con.execute("SELECT COUNT(*) FROM documentos").fetchone()[0]
    with con:
        importar_empresa(con, str(FC5), "00008")
    assert con.execute("SELECT COUNT(*) FROM documentos").fetchone()[0] == n1  # idempotente
    e = con.execute("SELECT * FROM empresas WHERE codigo='00008'").fetchone()
    d = con.execute("SELECT * FROM documentos WHERE empresa_id=? AND tipo='F' ORDER BY id DESC LIMIT 1", (e["id"],)).fetchone()
    assert float(d["total"]) != 0
    assert con.execute("SELECT COUNT(*) FROM lineas WHERE documento_id=?", (d["id"],)).fetchone()[0] >= 2

@pytest.mark.skipif(not FC5.exists(), reason="sin datos FactuCont")
def test_numeracion_y_creacion_y_pdf(con):
    from app import repo
    from app.fmt_pdf import render_pdf
    eid = con.execute("SELECT id FROM empresas WHERE codigo='00008'").fetchone()[0]
    sig = repo.siguiente_numero(con, eid, "F", "", "2026-11-02")
    assert sig.startswith("26")
    assert repo.siguiente_numero(con, eid, "F", "", "2027-01-05") == "270001"
    with con:
        did, num = repo.crear_factura(con, eid, {"fecha": "2026-11-02", "nombre_f": "PRUEBA SL", "nif": "B00000000"},
                                      [{"concepto": "Pintura", "cantidad": "2", "precio": "100", "iva": "21"}])
    assert num == sig
    d, ls, ps = repo.documento(con, did)
    assert d["total"] == "242.00" and d["origen"] == "nuevo"
    e = repo.empresa(con, eid)
    pdf = render_pdf(e["formato_factura"], e, d, ls, ps)
    assert pdf[:4] == b"%PDF"
    # reimportar conserva las facturas nuevas
    from app.importer import importar_empresa
    with con:
        importar_empresa(con, str(FC5), "00008")
    assert con.execute("SELECT COUNT(*) FROM documentos WHERE id=?", (did,)).fetchone()[0] == 1

@pytest.mark.skipif(not FC5.exists(), reason="sin datos FactuCont")
def test_paginas_web(con):
    from fastapi.testclient import TestClient
    import importlib, app.main
    importlib.reload(app.main)
    c = TestClient(app.main.app)
    eid = con.execute("SELECT id FROM empresas WHERE codigo='00008'").fetchone()[0]
    for u in ["/", f"/e/{eid}/clientes?q=a", f"/e/{eid}/documentos?tipo=F&anio=2026", f"/e/{eid}/nueva", f"/e/{eid}/verificacion"]:
        r = c.get(u); assert r.status_code == 200, u
    assert "ContFactu" in c.get("/").text
    r = c.post(f"/e/{eid}/nueva", data={"fecha": "2026-11-03", "nombre_f": "WEB SL", "n_lineas": "1", "concepto_0": "X",
               "cantidad_0": "1", "precio_0": "10", "iva_0": "21"}, follow_redirects=False)
    assert r.status_code == 303
    assert c.get(r.headers["location"].split("?")[0] + "/pdf").content[:4] == b"%PDF"
