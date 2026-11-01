"""Importador reejecutable desde las carpetas de FactuCont 5 (dBase IV, idioma 0x59 = ANSI español cp1252).

Uso:  python -m app.importer RUTA_A_FC5 [--empresas 00001,00008] [--db datos/facturas.db]

Re-ejecutar es seguro: borra y vuelve a cargar SOLO lo importado sin tocar (origen='factucont');
los documentos creados (origen='nuevo') o modificados (origen='editado') en ContFactu se conservan, y si un número
ya existe en ContFactu el documento de FactuCont NO se importa y se cuenta como conflicto.
"""
import argparse, glob, os, re, sys
from pathlib import Path
from dbfread import DBF
from .db import connect
from .calc import dec, r2, bases_desde_lineas, totales_cabecera

TABLAS_DOC = {  # fichero -> letra de tipo usada en RFALIN/REFERENCIA
    "ingreso1": "F", "albaran1": "A", "presupu1": "P", "gastos1": "G", "mostrad1": "M", "pedidos1": "D",
}
NOMBRES_TIPO = {"F": "Factura", "A": "Albarán", "P": "Presupuesto", "G": "Gasto", "M": "Venta mostrador", "D": "Pedido"}

def _find(carpeta, nombre):
    for f in os.listdir(carpeta):
        if f.lower() == nombre.lower():
            return os.path.join(carpeta, f)
    return None

def _leer(carpeta, base):
    f = _find(carpeta, base + ".dbf")
    if not f:
        return []
    return list(DBF(f, encoding="cp1252", ignore_missing_memofile=True, char_decode_errors="replace"))

def _s(v):
    return None if v is None else str(v).rstrip()

def _num(v):
    return None if v is None else format(dec(v).normalize(), "f")

def _fecha(v):
    return v.isoformat() if v else None

def leer_ficha_empresa(carpeta, codigo):
    """Los datos fiscales de la empresa están en EMPRESA.DBF (raíz); si falta, en el resumen '<cod>+01'."""
    datos = {}
    for cand in (f"{codigo}+01", f"{codigo}¬01"):
        p = os.path.join(carpeta, cand)
        if os.path.exists(p):
            for line in open(p, encoding="cp1252", errors="replace"):
                if "=" in line:
                    k, v = line.rstrip("\r\n").split("=", 1)
                    datos.setdefault(k.strip().upper(), v.strip().strip("'"))
    return datos

def formato_factura(fc5, codigo):
    ini = os.path.join(fc5, "formatos.ini")
    elegido = None
    if os.path.exists(ini):
        sec = None
        for line in open(ini, encoding="cp1252", errors="replace"):
            line = line.strip()
            if line.startswith("["):
                sec = line[1:-1]
            elif sec == codigo and line.lower().startswith("factura="):
                elegido = os.path.basename(line.split("=", 1)[1].replace("\\", "/"))
    carpeta = os.path.join(fc5, codigo)
    for cand in [elegido, "factura.fmt"] + sorted(glob.glob(os.path.join(carpeta, "*actura*.fmt"))):
        if cand:
            p = _find(carpeta, os.path.basename(cand))
            if p:
                return open(p, encoding="cp1252", errors="replace").read(), os.path.basename(p)
    return None, None

CLASES_FORMATO = {"factura": ["factura.fmt"], "presupuesto": ["presupuesto.fmt"], "albaran": ["albaran.fmt"], "recibo": ["recibo.fmt"]}

def formatos_empresa(fc5, codigo):
    """Devuelve {clase: (nombre, texto)} usando formatos.ini y, si no, los nombres estándar."""
    elegidos, sec = {}, None
    ini = os.path.join(fc5, "formatos.ini")
    if os.path.exists(ini):
        for line in open(ini, encoding="cp1252", errors="replace"):
            line = line.strip()
            if line.startswith("["):
                sec = line[1:-1]
            elif sec == codigo and "=" in line:
                k, v = line.split("=", 1)
                elegidos[k.strip().lower()] = os.path.basename(v.replace("\\", "/"))
    carpeta = os.path.join(fc5, codigo)
    res = {}
    for clase, defecto in CLASES_FORMATO.items():
        for cand in ([elegidos[clase]] if clase in elegidos else []) + defecto:
            p = _find(carpeta, cand)
            if p:
                res[clase] = (os.path.basename(p), open(p, encoding="cp1252", errors="replace").read())
                break
    return res

def importar_empresa(con, fc5, codigo):
    carpeta = os.path.join(fc5, codigo)
    ficha = leer_ficha_empresa(carpeta, codigo)
    fmt, fmt_nombre = formato_factura(fc5, codigo)
    con.execute("""INSERT INTO empresas(codigo,nombre,direccion,ciudad,nif,actividad,ccc,bic,formato_factura,origen)
        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre, direccion=excluded.direccion,
        ciudad=excluded.ciudad, nif=excluded.nif, actividad=excluded.actividad, ccc=excluded.ccc, bic=excluded.bic,
        formato_factura=excluded.formato_factura, origen=excluded.origen""",
        (codigo, ficha.get("NOMBRE") or f"Empresa {codigo}", ficha.get("DIRECCION"), ficha.get("CIUDAD"), ficha.get("CIF"),
         ficha.get("ACTIVIDAD1"), ficha.get("CCC"), ficha.get("BIC"), fmt, carpeta))
    eid = con.execute("SELECT id FROM empresas WHERE codigo=?", (codigo,)).fetchone()[0]
    for clase, (nombre, texto) in formatos_empresa(fc5, codigo).items():
        con.execute("INSERT OR REPLACE INTO formatos(empresa_id,clase,nombre,texto) VALUES(?,?,?,?)", (eid, clase, nombre, texto))
    # limpiar lo importado previamente
    con.execute("DELETE FROM documentos WHERE empresa_id=? AND origen='factucont'", (eid,))
    con.execute("DELETE FROM plazos WHERE empresa_id=? AND (documento_id IS NULL OR documento_id NOT IN (SELECT id FROM documentos))", (eid,))
    # clientes/proveedores: se actualizan por código (INSERT OR REPLACE), sin borrar los dados de alta en ContFactu
    con.execute("DELETE FROM verificacion WHERE documento_id NOT IN (SELECT id FROM documentos)")

    for r in _leer(carpeta, "cliente"):
        con.execute("""INSERT OR REPLACE INTO clientes(empresa_id,codigo,nombre,direccion,ciudad,nombre_f,direccion_f,ciudad_f,nif,
            telefono,movil,fax,email,contacto,descuento,recargo,retiene,exento,forma_pago,dias_pago,domiciliacion,ccc,bic,libre1,libre2,libre3)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, _s(r["CODIGO"]), _s(r["NOMBRE"]), _s(r["DIRECCION"]), _s(r["CIUDAD"]), _s(r["NOMBREF"]), _s(r["DIRECCIONF"]),
             _s(r["CIUDADF"]), _s(r["CIF"]), _s(r["TELEFONO"]), _s(r["MOVIL"]), _s(r["FAX"]), _s(r["CORREOE"]), _s(r["CONTACTO"]),
             _num(r["DESCUENTO"]), int(bool(r["RECARGO"])), int(bool(r["RETIENE"])), int(bool(r["EXENTO"])), _s(r["FORMAPAGO"]),
             _s(r["DIASPAGO"]), _s(r["DOMICILIA"]), _s(r["CCC"]), _s(r["BIC"]), _s(r["LIBRE1"]), _s(r["LIBRE2"]), _s(r["LIBRE3"])))
    for r in _leer(carpeta, "proveedo"):
        con.execute("""INSERT OR REPLACE INTO proveedores(empresa_id,codigo,nombre,direccion,ciudad,nombre_f,direccion_f,ciudad_f,nif,
            telefono,movil,email,contacto,retencion,exento,forma_pago,dias_pago) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, _s(r["CODIGO"]), _s(r["NOMBRE"]), _s(r["DIRECCION"]), _s(r["CIUDAD"]), _s(r["NOMBREF"]), _s(r["DIRECCIONF"]),
             _s(r["CIUDADF"]), _s(r["CIF"]), _s(r["TELEFONO"]), _s(r["MOVIL"]), _s(r["CORREOE"]), _s(r["CONTACTO"]),
             _num(r["RETENCION"]), int(bool(r["EXENTO"])), _s(r["FORMAPAGO"]), _s(r["DIASPAGO"])))

    # líneas agrupadas por clave tipo+NUMERO(10)
    lineas = {}
    for r in _leer(carpeta, "conteni1"):
        rf = r["RFALIN"] or ""
        lineas.setdefault(rf[:11], []).append((rf[11:], r))
    docs = {}
    stats = {"documentos": 0, "lineas": 0, "plazos": 0, "huerfanas": 0, "conflictos": 0}
    existentes = {(t, r) for t, r in con.execute("SELECT tipo, numero_raw FROM documentos WHERE empresa_id=?", (eid,))}
    for tabla, tipo in TABLAS_DOC.items():
        for r in _leer(carpeta, tabla):
            raw = (r["NUMERO"] or "").ljust(10)
            clave = tipo + raw
            if not raw.strip():  # documentos sin número (borradores): clave interna única
                sin_num = stats.setdefault("sin_numero", 0) + 1
                stats["sin_numero"] = sin_num
                raw = f"~SINNUM{sin_num:03d}"
            g = lambda k: r[k] if k in r else None
            if (tipo, raw) in existentes:  # ya existe en ContFactu (creado o editado allí): no se pisa
                stats["conflictos"] += 1
                lineas.pop(clave, None)
                continue
            cur = con.execute("""INSERT INTO documentos(empresa_id,tipo,numero_raw,serie,numero,fecha,fecha_operacion,nombre_f,direccion_f,
                ciudad_f,nif,base1,iva1,re1,base2,iva2,re2,base3,iva3,re3,exento,iva_incluido,descuento,retencion,retenido,pendiente,
                forma_pago,dias_pago,domiciliacion,ccc,bic,facturado,num_factura_proveedor,deducible,epigrafe,origen)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'factucont')""",
                (eid, tipo, raw, raw[:3].strip(), raw[3:].strip(), _fecha(g("FECHA")), _fecha(g("FECHAOPERA")), _s(g("NOMBREF")),
                 _s(g("DIRECCIONF")), _s(g("CIUDADF")), _s(g("CIF")),
                 _num(g("BASE1")), _num(g("IVA1")), _num(g("RE1")), _num(g("BASE2")), _num(g("IVA2")), _num(g("RE2")),
                 _num(g("BASE3")), _num(g("IVA3")), _num(g("RE3")), int(bool(g("EXENTO"))), int(bool(g("IVAINCL"))),
                 _num(g("DESCUENTO")), _num(g("RETENCION")), _num(g("RETENIDO")), _num(g("PENDIENTE")), _s(g("FORMAPAGO")),
                 _s(g("DIASPAGO")), _s(g("DOMICILIA")), _s(g("CCC")), _s(g("BIC")),
                 None if g("FACTURADO") is None else int(bool(g("FACTURADO"))), _s(g("NUMFACTURA")),
                 g("DEDUCIBLE"), g("EPIGRAFE")))
            did = cur.lastrowid
            docs[clave] = did
            stats["documentos"] += 1
            ls = sorted(lineas.pop(clave, []), key=lambda x: x[0])
            for orden, (_, l) in enumerate(ls, 1):
                con.execute("""INSERT INTO lineas(documento_id,orden,codigo,concepto,cantidad,precio,descuento,iva,comentario,fecha)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""", (did, orden, _s(l["CODIGO"]), _s(l["CONCEPTO"]), _num(l["CANTIDAD"]), _num(l["PRECIO"]),
                    _num(l["DESCUENTO"]), _num(l["IVA"]), int(bool(l["COMENTARIO"])), _fecha(l["FECHA"])))
                stats["lineas"] += 1
            tot = totales_cabecera(dict(con.execute("SELECT * FROM documentos WHERE id=?", (did,)).fetchone()))
            con.execute("UPDATE documentos SET total=? WHERE id=?", (str(tot["total"]), did))
    stats["huerfanas"] = sum(len(v) for v in lineas.values())
    for r in _leer(carpeta, "plazos1"):
        ref = (r["REFERENCIA"] or "")
        did = docs.get(ref[:1] + ref[1:].ljust(10))
        if did is None and (ref[:1] + ref[1:].ljust(10)) not in docs and any(t == ref[:1] for t in TABLAS_DOC.values()):
            if con.execute("SELECT 1 FROM documentos WHERE empresa_id=? AND tipo=? AND numero_raw=?", (eid, ref[:1], ref[1:].ljust(10))).fetchone():
                continue  # plazo de un documento en conflicto: se conserva el de ContFactu
        tipo_p = _s(r["TIPO"]) or ""
        cobrado = _num(r["IMPORTE"]) if tipo_p == "A" else "0"  # 'A' = vencimiento ya cobrado en FactuCont
        con.execute("INSERT INTO plazos(documento_id,empresa_id,referencia,tipo,fecha,concepto,importe,cobrado) VALUES(?,?,?,?,?,?,?,?)",
                    (did, eid, ref, tipo_p, _fecha(r["FECHA"]), _s(r["CONCEPTO"]), _num(r["IMPORTE"]), cobrado))
        stats["plazos"] += 1
    stats["verificacion"] = verificar_empresa(con, eid)
    return eid, stats, fmt_nombre

def verificar_empresa(con, eid):
    """Recalcula bases desde líneas y las compara con la cabecera (tolerancia 0,01 € por tipo)."""
    n_ok = n_mal = n_sin = 0
    for d in con.execute("SELECT * FROM documentos WHERE empresa_id=? AND origen='factucont'", (eid,)).fetchall():
        d = dict(d)
        ls = [dict(x) for x in con.execute("SELECT * FROM lineas WHERE documento_id=?", (d["id"],))]
        cab = {}
        for i in (1, 2, 3):
            b = dec(d[f"base{i}"])
            if b != 0:
                k = dec(d[f"iva{i}"]).normalize()
                cab[k] = cab.get(k, 0) + r2(b)
        if not [l for l in ls if not l["comentario"]]:
            if cab:
                n_sin += 1
                con.execute("INSERT INTO verificacion(empresa_id,documento_id,tipo,numero,detalle) VALUES(?,?,?,?,?)",
                            (eid, d["id"], d["tipo"], d["numero"], f"Sin líneas; cabecera {dict((str(k),str(v)) for k,v in cab.items())}"))
            continue
        calc = bases_desde_lineas(ls, d["descuento"], d["iva_incluido"])
        claves = set(cab) | set(calc)
        difs = {str(k): (str(cab.get(k, 0)), str(calc.get(k, 0))) for k in claves if abs(dec(cab.get(k, 0)) - dec(calc.get(k, 0))) > dec("0.011")}
        if difs:
            n_mal += 1
            con.execute("INSERT INTO verificacion(empresa_id,documento_id,tipo,numero,detalle) VALUES(?,?,?,?,?)",
                        (eid, d["id"], d["tipo"], d["numero"], "IVA%: (cabecera, líneas) " + repr(difs)))
        else:
            n_ok += 1
    return {"cuadran": n_ok, "descuadran": n_mal, "sin_lineas": n_sin}

def empresas_con_datos(fc5):
    res = []
    for c in sorted(os.listdir(fc5)):
        p = os.path.join(fc5, c)
        if re.fullmatch(r"\d{5}", c) and os.path.isdir(p):
            if any(len(_leer(p, t)) for t in list(TABLAS_DOC) + ["cliente"]):
                res.append(c)
    return res

def importar_fc5(con, fc5, codigos=None):
    """Importa todas las empresas con datos de una carpeta FC5. Devuelve [(código, nombre, estadísticas)]."""
    res = []
    for c in codigos or empresas_con_datos(fc5):
        propia = con.execute("SELECT nombre FROM empresas WHERE codigo=? AND origen='nuevo'", (c,)).fetchone()
        if propia:  # nunca mezclar FactuCont con una empresa dada de alta en ContFactu
            res.append((c, propia[0], {"omitida": f"No se importa la empresa {c} de FactuCont: ese código ya lo usa «{propia[0]}», "
                                       "creada en ContFactu. Cambie el código de esa empresa (menú Empresa) y vuelva a importar."}))
            continue
        eid, st, _ = importar_empresa(con, fc5, c)
        res.append((c, con.execute("SELECT nombre FROM empresas WHERE id=?", (eid,)).fetchone()[0], st))
    return res

def main(argv=None):
    ap = argparse.ArgumentParser(description="Importa datos de FactuCont 5")
    ap.add_argument("fc5", help="Carpeta FC5 de FactuCont (p. ej. C:\\Binarema\\FC5)")
    ap.add_argument("--empresas", help="Lista separada por comas; por defecto todas las que tengan datos")
    ap.add_argument("--db")
    a = ap.parse_args(argv)
    con = connect(a.db)
    cods = a.empresas.split(",") if a.empresas else empresas_con_datos(a.fc5)
    with con:
        for c in cods:
            eid, st, fmt = importar_empresa(con, a.fc5, c)
            print(f"Empresa {c}: {st} formato={fmt}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
