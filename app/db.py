"""Base de datos SQLite de ContFactu. Los importes se guardan como texto decimal exacto (sin errores de coma flotante)."""
import sqlite3, os, sys
from pathlib import Path

def data_dir():
    """Carpeta de datos: %APPDATA%\\ContFactu en el .exe; ./datos en desarrollo. CONTFACTU_DATA la fuerza."""
    if os.environ.get("CONTFACTU_DATA"):
        return Path(os.environ["CONTFACTU_DATA"])
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "ContFactu"
    return Path(__file__).resolve().parent.parent / "datos"

def db_path():
    return Path(os.environ.get("CONTFACTU_DB") or data_dir() / "contfactu.db")

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS empresas (
  id INTEGER PRIMARY KEY,
  codigo TEXT UNIQUE NOT NULL,          -- carpeta FactuCont (00001...)
  nombre TEXT, direccion TEXT, ciudad TEXT, nif TEXT, actividad TEXT,
  ccc TEXT, bic TEXT,
  formato_factura TEXT,                 -- texto .fmt original (diseño)
  origen TEXT,                          -- ruta de importación, o 'nuevo' si se creó en ContFactu
  cp TEXT, provincia TEXT, telefono TEXT, email TEXT,
  serie_defecto TEXT,                   -- serie de facturas por defecto ('' = sin serie)
  contador_inicial INTEGER,             -- primer correlativo de facturas (empresa que viene de otro programa)
  ivas TEXT,                            -- tipos de IVA habituales, p. ej. '21,10,4,0' (el primero, por defecto)
  logo TEXT,                            -- nombre del archivo del logotipo en la carpeta de datos (logos/)
  creada TEXT
);
CREATE TABLE IF NOT EXISTS clientes (
  id INTEGER PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
  codigo TEXT, nombre TEXT, direccion TEXT, ciudad TEXT,
  nombre_f TEXT, direccion_f TEXT, ciudad_f TEXT, nif TEXT,
  telefono TEXT, movil TEXT, fax TEXT, email TEXT, contacto TEXT,
  descuento TEXT, recargo INTEGER, retiene INTEGER, exento INTEGER,
  forma_pago TEXT, dias_pago TEXT, domiciliacion TEXT, ccc TEXT, bic TEXT,
  libre1 TEXT, libre2 TEXT, libre3 TEXT,
  UNIQUE(empresa_id, codigo)
);
CREATE TABLE IF NOT EXISTS proveedores (
  id INTEGER PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
  codigo TEXT, nombre TEXT, direccion TEXT, ciudad TEXT,
  nombre_f TEXT, direccion_f TEXT, ciudad_f TEXT, nif TEXT,
  telefono TEXT, movil TEXT, email TEXT, contacto TEXT, retencion TEXT, exento INTEGER,
  forma_pago TEXT, dias_pago TEXT,
  UNIQUE(empresa_id, codigo)
);
-- tipo: F factura emitida, A albarán, P presupuesto, G gasto, M mostrador, D pedido
CREATE TABLE IF NOT EXISTS documentos (
  id INTEGER PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL,
  numero_raw TEXT NOT NULL,             -- NUMERO tal cual en FactuCont (10 car.)
  serie TEXT NOT NULL DEFAULT '',       -- 3 primeros caracteres
  numero TEXT NOT NULL,                 -- número visible (sin serie)
  fecha TEXT, fecha_operacion TEXT,
  nombre_f TEXT, direccion_f TEXT, ciudad_f TEXT, nif TEXT,
  cliente_codigo TEXT,
  base1 TEXT, iva1 TEXT, re1 TEXT, base2 TEXT, iva2 TEXT, re2 TEXT, base3 TEXT, iva3 TEXT, re3 TEXT,
  exento INTEGER, iva_incluido INTEGER, descuento TEXT, retencion TEXT, retenido TEXT, pendiente TEXT,
  forma_pago TEXT, dias_pago TEXT, domiciliacion TEXT, ccc TEXT, bic TEXT,
  facturado INTEGER, num_factura_proveedor TEXT,
  facturado_en_id INTEGER,              -- factura generada a partir de este presupuesto/albarán
  deducible INTEGER, epigrafe INTEGER,  -- gastos (FactuCont)
  rect_original_id INTEGER,             -- rectificativas: factura rectificada
  rect_tipo TEXT,                       -- 'I' por diferencias, 'S' por sustitución
  rect_motivo TEXT,
  rect_base_original TEXT, rect_cuota_original TEXT,
  rect_pendiente_original TEXT,         -- (sustitución) pendiente que tenía la original al rectificarla
  total TEXT,                           -- calculado al importar/crear
  origen TEXT NOT NULL DEFAULT 'factucont',  -- 'factucont' o 'nuevo'
  -- Preparado para VeriFactu (fase 2, aún sin uso):
  vf_tipo_factura TEXT,                 -- F1, F2 (simplificada), R1..R5 (rectificativas)
  vf_huella TEXT,                       -- SHA-256 del registro de alta
  vf_huella_anterior TEXT,              -- huella del registro anterior (encadenamiento)
  vf_fecha_hora_huso TEXT,              -- fecha/hora de generación del registro con huso
  vf_estado TEXT,                       -- pendiente / enviado / aceptado / rechazado
  vf_csv TEXT,                          -- código seguro de verificación devuelto por la AEAT
  vf_qr_url TEXT,                       -- URL de cotejo que va en el QR
  UNIQUE(empresa_id, tipo, numero_raw)
);
CREATE INDEX IF NOT EXISTS ix_doc_fecha ON documentos(empresa_id, tipo, fecha);
CREATE TABLE IF NOT EXISTS lineas (
  id INTEGER PRIMARY KEY, documento_id INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
  orden INTEGER NOT NULL, codigo TEXT, concepto TEXT, cantidad TEXT, precio TEXT,
  descuento TEXT, iva TEXT, comentario INTEGER, fecha TEXT
);
CREATE TABLE IF NOT EXISTS plazos (
  id INTEGER PRIMARY KEY, documento_id INTEGER REFERENCES documentos(id) ON DELETE CASCADE,
  empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
  referencia TEXT, tipo TEXT, fecha TEXT, concepto TEXT, importe TEXT,
  cobrado TEXT NOT NULL DEFAULT '0'     -- importe ya cobrado de este vencimiento
);
-- tipo de plazo: '1' cargo (importe total, negativo), '' vencimiento, 'A' vencimiento cobrado/anticipo (FactuCont)
CREATE TABLE IF NOT EXISTS cobros (
  id INTEGER PRIMARY KEY, documento_id INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
  plazo_id INTEGER REFERENCES plazos(id) ON DELETE SET NULL,
  fecha TEXT NOT NULL, importe TEXT NOT NULL, forma TEXT, nota TEXT
);
CREATE TABLE IF NOT EXISTS formatos (
  empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
  clase TEXT NOT NULL,                  -- factura, presupuesto, albaran, recibo
  nombre TEXT, texto TEXT, PRIMARY KEY(empresa_id, clase)
);
-- Registro de eventos/facturación VeriFactu (fase 2)
CREATE TABLE IF NOT EXISTS vf_registros (
  id INTEGER PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id),
  documento_id INTEGER REFERENCES documentos(id),
  tipo_registro TEXT,                   -- alta / anulacion / evento
  contenido_xml TEXT, huella TEXT, huella_anterior TEXT, fecha_hora_huso TEXT,
  estado_envio TEXT, respuesta TEXT
);
CREATE TABLE IF NOT EXISTS verificacion (
  id INTEGER PRIMARY KEY, empresa_id INTEGER, documento_id INTEGER,
  tipo TEXT, numero TEXT, detalle TEXT
);
"""

COLUMNAS_NUEVAS = {  # migración de bases creadas con versiones anteriores
    "documentos": ["facturado_en_id INTEGER", "deducible INTEGER", "epigrafe INTEGER", "rect_original_id INTEGER",
                   "rect_tipo TEXT", "rect_motivo TEXT", "rect_base_original TEXT", "rect_cuota_original TEXT", "rect_pendiente_original TEXT"],
    "plazos": ["cobrado TEXT NOT NULL DEFAULT '0'"],
    "empresas": ["cp TEXT", "provincia TEXT", "telefono TEXT", "email TEXT", "serie_defecto TEXT", "contador_inicial INTEGER",
                 "ivas TEXT", "logo TEXT", "creada TEXT"],
}

def connect(path=None):
    p = Path(path or db_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    for tabla, cols in COLUMNAS_NUEVAS.items():
        existe = con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (tabla,)).fetchone()
        if existe:
            actuales = {r[1] for r in con.execute(f"PRAGMA table_info({tabla})")}
            for c in cols:
                if c.split()[0] not in actuales:
                    con.execute(f"ALTER TABLE {tabla} ADD COLUMN {c}")
    con.executescript(SCHEMA)
    return con
