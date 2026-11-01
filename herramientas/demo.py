"""Crea una base de demostración con datos FICTICIOS (para capturas, formación o pruebas sin datos reales).
Uso:  python -m herramientas.demo datos_demo/demo.db [carpeta FC5 para copiar los diseños .fmt]"""
import sys
from pathlib import Path
from app.db import connect
from app import repo

def L(c, n, p, iva="21"):
    return {"concepto": c, "cantidad": str(n), "precio": str(p), "iva": iva}

def crear(ruta, fc5=None):
    ruta = Path(ruta)
    if ruta.exists():
        ruta.unlink()
    con = connect(ruta)
    with con:
        con.execute("""INSERT INTO empresas(id,codigo,nombre,direccion,ciudad,nif,actividad) VALUES
            (1,'90001','Ferretería Ejemplo, S.L.','C/ Mayor, 1','28001 Madrid','B00000000','Ferretería y suministros')""")
        con.execute("INSERT INTO clientes(empresa_id,codigo,nombre,nif,direccion,ciudad,forma_pago) VALUES(1,'1','Construcciones Demo, S.A.','A00000001','Avda. Ficticia, 10','28002 Madrid','Recibo a 30 días')")
        con.execute("INSERT INTO clientes(empresa_id,codigo,nombre,nif,direccion,ciudad,recargo) VALUES(1,'2','Bazar La Prueba','00000002T','Plaza Inventada, 3','45001 Toledo',1)")
        if fc5:
            for clase, nombre in (("factura", "factura.fmt"), ("albaran", "Albaran.fmt"), ("presupuesto", "Presupuesto.fmt"), ("recibo", "Recibo.fmt")):
                p = Path(fc5) / "00008" / nombre
                if p.exists():
                    con.execute("INSERT INTO formatos VALUES(1,?,?,?)", (clase, nombre, p.read_text(encoding="cp1252")))
            con.execute("UPDATE empresas SET formato_factura=(SELECT texto FROM formatos WHERE clase='factura')")
        c1 = {"nombre_f": "Construcciones Demo, S.A.", "nif": "A00000001", "direccion_f": "Avda. Ficticia, 10", "ciudad_f": "28002 Madrid",
              "cliente_codigo": "1", "forma_pago": "Recibo a 30 días", "domiciliacion": "Banco Ficticio", "ccc": "ES91 2100 0418 4502 0005 1332"}
        c2 = {"nombre_f": "Bazar La Prueba", "nif": "00000002T", "direccion_f": "Plaza Inventada, 3", "ciudad_f": "45001 Toledo", "cliente_codigo": "2", "re": True}
        g = lambda t, f, d, ls: repo.guardar_documento(con, 1, t, dict(d, fecha=f), ls)
        f1 = g("F", "2026-07-03", c1, [L("Taladro percutor 800 W", 2, "89.90"), L("Juego de brocas HSS 19 piezas", 4, "14.50")])
        f2 = g("F", "2026-07-15", c2, [L("Bombillas LED E27 10 W", 50, "2.10"), L("Guía de bricolaje (libro)", 5, "12.00", "4")])
        f3 = g("F", "2026-08-02", c1, [L("Escalera aluminio 7 peldaños", 1, "119.00"), L("Cinta americana 50 m", 12, "4.75")])
        g("F", "2026-09-10", c2, [L("Pilas alcalinas AA (pack 4)", 30, "3.20")])
        repo.registrar_cobro(con, f1, "150.00", "2026-07-20", "Transferencia", "Pago a cuenta")
        repo.registrar_cobro(con, f2, repo.doc(con, f2)["pendiente"], "2026-08-01", "Efectivo")
        repo.crear_rectificativa(con, f3, "I", "Devolución de la escalera (defecto de fábrica)", "R4", "2026-08-20",
                                 [L("Escalera aluminio 7 peldaños (devolución)", -1, "119.00")])
        a1 = g("A", "2026-09-02", c1, [L("Sacos de cemento 25 kg", 20, "6.40"), L("Arena lavada (big bag)", 2, "48.00")])
        a2 = g("A", "2026-09-09", c1, [L("Ladrillo hueco doble (palé)", 3, "155.00")])
        g("A", "2026-09-16", c1, [L("Mortero cola 25 kg", 10, "9.80")])
        g("A", "2026-09-20", c2, [L("Candados latón 40 mm", 12, "7.90")])
        repo.facturar(con, [a1, a2], "2026-09-30")
        g("P", "2026-10-05", c1, [L("Instalación de estanterías metálicas", 1, "640.00"), L("Estanterías 5 baldas", 8, "59.00")])
        g("G", "2026-07-05", {"nombre_f": "Distribuidora Mayorista Demo", "nif": "B00000003", "num_factura_proveedor": "DM-2026-0411"},
          [L("Compra de mercancía", 1, "1450.00")])
        g("G", "2026-08-12", {"nombre_f": "Suministros Eléctricos Demo", "nif": "B00000004", "num_factura_proveedor": "F/889"},
          [L("Electricidad local julio", 1, "182.35")])
    return con

if __name__ == "__main__":
    crear(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print("Base de demostración creada en", sys.argv[1])
