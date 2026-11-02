"""Copias de seguridad de la carpeta de datos en un .zip con fecha y hora.

Contenido del .zip:
- contfactu.db      copia CONSISTENTE de la base SQLite (API de copia en caliente de sqlite3, no una copia del archivo)
- logos/            logotipos de las empresas
- contfactu-copia.json   programa, versión, esquema, fecha y recuento de empresas/documentos
Los ajustes (carpeta de copias, avisos, configuración de correo…) viven dentro de la base, así que van en la copia.
Las contraseñas del correo NO: están en el Administrador de credenciales de Windows.

Copias automáticas (antes de actualizar de versión y antes de restaurar): <carpeta de datos>/copias-automaticas/.
"""
from urllib.parse import quote
import datetime, json, os, shutil, sqlite3, sys, tempfile, zipfile
from pathlib import Path

MANIFIESTO = "contfactu-copia.json"
NOMBRE_DB = "contfactu.db"
CONSERVAR_AUTOMATICAS = 20
DIAS_AVISO_DEFECTO = 7

class ErrorCopia(Exception):
    """Error explicable al usuario."""

def carpeta_documentos():
    """Carpeta «Documentos» real del usuario (en Windows puede estar redirigida, p. ej. a OneDrive)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:   # CSIDL_PERSONAL
                return Path(buf.value)
        except Exception:
            pass
    return Path.home() / "Documents"

def carpeta_defecto():
    return carpeta_documentos() / "ContFactu-Copias"

def _marca():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

def _volcar(origen, destino):
    """Copia consistente de una base SQLite aunque esté abierta (sqlite3.Connection.backup)."""
    src = sqlite3.connect(f"file:{quote(Path(origen).as_posix(), safe='/:')}?mode=ro", uri=True)
    dst = sqlite3.connect(destino)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()

def _recuento(ruta_db):
    con = sqlite3.connect(f"file:{quote(Path(ruta_db).as_posix(), safe='/:')}?mode=ro", uri=True)
    try:
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        res = {}
        for t in ("empresas", "documentos", "clientes", "proveedores"):
            res[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if t in tablas else 0
        res["empresas_nombres"] = [r[0] for r in con.execute("SELECT nombre FROM empresas ORDER BY codigo")] if "empresas" in tablas else []
        v = {}
        if "ajustes" in tablas:
            v = dict(con.execute("SELECT clave, valor FROM ajustes WHERE clave IN ('version','esquema')").fetchall())
        res["version"], res["esquema"] = v.get("version"), int(v["esquema"]) if v.get("esquema") else None
        return res
    finally:
        con.close()

def crear_zip(destino_zip, db=None, datos=None):
    """Escribe la copia en destino_zip (primero en un .part y luego se renombra: nunca queda un .zip a medias)."""
    from .db import db_path, data_dir
    from . import __version__
    db = Path(db or db_path()); datos = Path(datos or data_dir())
    if not db.exists():
        raise ErrorCopia("Todavía no hay datos que copiar.")
    destino_zip = Path(destino_zip)
    destino_zip.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="contfactu_copia_"))
    parte = destino_zip.with_name(destino_zip.name + ".part")
    try:
        volcado = tmp / NOMBRE_DB
        _volcar(db, volcado)
        info = _recuento(volcado)
        manifiesto = {"programa": "ContFactu", "version_programa": __version__, "version_datos": info["version"],
                      "esquema": info["esquema"], "fecha": datetime.datetime.now().isoformat(timespec="seconds"),
                      "empresas": info["empresas"], "documentos": info["documentos"], "nombres": info["empresas_nombres"]}
        with zipfile.ZipFile(parte, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(volcado, NOMBRE_DB)
            logos = datos / "logos"
            if logos.is_dir():
                for f in sorted(logos.iterdir()):
                    if f.is_file():
                        z.write(f, f"logos/{f.name}")
            z.writestr(MANIFIESTO, json.dumps(manifiesto, ensure_ascii=False, indent=2))
        os.replace(parte, destino_zip)
        return destino_zip
    except OSError as ex:
        raise ErrorCopia(f"No he podido escribir la copia en «{destino_zip.parent}»: {ex.strerror or ex}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if parte.exists():
            try: parte.unlink()
            except OSError: pass

def _nombre_libre(carpeta, prefijo):
    base = f"{prefijo}-{_marca()}"
    p, n = Path(carpeta) / f"{base}.zip", 2
    while p.exists():
        p = Path(carpeta) / f"{base}-{n}.zip"; n += 1
    return p

def crear_copia(con, carpeta=None):
    """Copia manual («un clic»). Recuerda la carpeta y la fecha de la última copia. Devuelve la ruta del .zip."""
    from .db import ajuste, poner_ajuste
    carpeta = Path(str(carpeta).strip().strip('"')) if carpeta and str(carpeta).strip() else \
        Path(ajuste(con, "copia_carpeta") or carpeta_defecto())
    if not carpeta.is_absolute():
        raise ErrorCopia(f"Indique una carpeta completa (p. ej. {carpeta_defecto()}).")
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
    except OSError as ex:
        raise ErrorCopia(f"No he podido crear la carpeta «{carpeta}»: {ex.strerror or ex}")
    ruta = crear_zip(_nombre_libre(carpeta, "ContFactu-copia"))
    with con:
        poner_ajuste(con, "copia_carpeta", str(carpeta))
        poner_ajuste(con, "copia_ultima", datetime.datetime.now().isoformat(timespec="seconds"))
        poner_ajuste(con, "copia_ultima_archivo", str(ruta))
    return ruta

def carpeta_automaticas():
    from .db import data_dir
    return data_dir() / "copias-automaticas"

def copia_automatica(motivo, db=None):
    """Copia de seguridad que hace el programa por su cuenta (antes de actualizar o de restaurar)."""
    carpeta = carpeta_automaticas()
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = crear_zip(_nombre_libre(carpeta, f"ContFactu-{motivo}"), db=db)
    zips = sorted(carpeta.glob("ContFactu-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for viejo in zips[CONSERVAR_AUTOMATICAS:]:
        try: viejo.unlink()
        except OSError: pass
    return ruta

def leer_copia(ruta_zip):
    """Comprueba un .zip de copia y devuelve su resumen (para la pantalla de confirmación). Lanza ErrorCopia si no vale."""
    from .db import ESQUEMA
    ruta_zip = Path(ruta_zip)
    if not ruta_zip.is_file():
        raise ErrorCopia(f"No encuentro el archivo «{ruta_zip}».")
    try:
        with zipfile.ZipFile(ruta_zip) as z:
            nombres = set(z.namelist())
            if NOMBRE_DB not in nombres:
                raise ErrorCopia("El archivo no es una copia de ContFactu (no contiene contfactu.db).")
            man = json.loads(z.read(MANIFIESTO).decode("utf-8")) if MANIFIESTO in nombres else {}
            tmp = Path(tempfile.mkdtemp(prefix="contfactu_leer_"))
            try:
                z.extract(NOMBRE_DB, tmp)
                con = sqlite3.connect(f"file:{quote((tmp / NOMBRE_DB).as_posix(), safe='/:')}?mode=ro", uri=True)
                try:
                    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
                finally:
                    con.close()
                if ok != "ok":
                    raise ErrorCopia(f"La base de datos de la copia está dañada ({ok}).")
                info = _recuento(tmp / NOMBRE_DB)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            logos = sorted(n for n in nombres if n.startswith("logos/") and not n.endswith("/"))
    except zipfile.BadZipFile:
        raise ErrorCopia("El archivo no es un .zip válido.")
    except sqlite3.DatabaseError as ex:
        raise ErrorCopia(f"La base de datos de la copia no se puede leer: {ex}")
    if info["esquema"] and info["esquema"] > ESQUEMA:
        raise ErrorCopia(f"La copia es de una versión más moderna de ContFactu ({info['version']}). Actualice el programa antes de restaurarla.")
    return {"archivo": str(ruta_zip), "fecha": man.get("fecha"), "version": info["version"] or man.get("version_programa") or "anterior a 0.0.4",
            "empresas": info["empresas"], "documentos": info["documentos"], "clientes": info["clientes"],
            "proveedores": info["proveedores"], "nombres": info["empresas_nombres"], "logos": len(logos)}

def restaurar(ruta_zip):
    """Sustituye los datos actuales por los de la copia. ANTES hace una copia automática de los datos actuales.
    Devuelve (resumen de la copia restaurada, ruta de la copia de seguridad previa)."""
    from .db import db_path, data_dir, olvidar_preparacion, _preparar
    info = leer_copia(ruta_zip)
    db = db_path()
    previa = copia_automatica("antes-de-restaurar") if db.exists() else None
    tmp = Path(tempfile.mkdtemp(prefix="contfactu_rest_"))
    try:
        with zipfile.ZipFile(ruta_zip) as z:
            z.extract(NOMBRE_DB, tmp)
            logos_zip = [n for n in z.namelist() if n.startswith("logos/") and not n.endswith("/")]
            # solo nombres simples dentro de logos/ (nada de rutas con «..»)
            logos = []
            for n in logos_zip:
                nombre = os.path.basename(n)
                if nombre and nombre == n[len("logos/"):] and not nombre.startswith("."):
                    (tmp / "logos").mkdir(exist_ok=True)
                    (tmp / "logos" / nombre).write_bytes(z.read(n))
                    logos.append(nombre)
        db.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(tmp / NOMBRE_DB)
        dst = sqlite3.connect(db)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        carpeta_logos = data_dir() / "logos"
        if carpeta_logos.exists():
            shutil.rmtree(carpeta_logos)
        if logos:
            shutil.copytree(tmp / "logos", carpeta_logos)
        olvidar_preparacion(db)
        _preparar(db, sin_copia=True)   # pone al día el esquema si la copia es de una versión anterior
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return info, previa

def dias_desde_ultima(con, ahora=None):
    """Días desde la última copia manual, o None si nunca se ha hecho."""
    from .db import ajuste
    u = ajuste(con, "copia_ultima")
    if not u:
        return None
    try:
        return ((ahora or datetime.datetime.now()) - datetime.datetime.fromisoformat(u)).days
    except ValueError:
        return None

def dias_aviso(con):
    from .db import ajuste
    try:
        return max(0, int(ajuste(con, "copia_dias", DIAS_AVISO_DEFECTO)))
    except (TypeError, ValueError):
        return DIAS_AVISO_DEFECTO

def necesita_aviso(con, ahora=None):
    """True si conviene recordar que se haga una copia (hay datos y la última copia es más antigua que el plazo)."""
    n = dias_aviso(con)
    if n == 0 or not con.execute("SELECT 1 FROM empresas").fetchone():
        return False
    d = dias_desde_ultima(con, ahora)
    return d is None or d >= n
