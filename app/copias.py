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
    """Días desde la última copia (manual, o automática si el usuario las activó), o None si nunca se ha hecho."""
    from .db import ajuste
    fechas = []
    for clave in ("copia_ultima", "copia_auto_ultima"):
        try:
            if ajuste(con, clave):
                fechas.append(datetime.datetime.fromisoformat(ajuste(con, clave)))
        except ValueError:
            pass
    if not fechas:
        return None
    return ((ahora or datetime.datetime.now()) - max(fechas)).days

def dias_aviso(con):
    from .db import ajuste
    try:
        return max(0, int(ajuste(con, "copia_dias", DIAS_AVISO_DEFECTO)))
    except (TypeError, ValueError):
        return DIAS_AVISO_DEFECTO

def necesita_aviso(con, ahora=None):
    """True si conviene recordar que se haga una copia (hay datos y la última copia es más antigua que el plazo)."""
    from .db import ajuste
    n = dias_aviso(con)
    if n == 0 or ajuste(con, "copia_no_recordar") == "1" or not con.execute("SELECT 1 FROM empresas").fetchone():
        return False
    d = dias_desde_ultima(con, ahora)
    return d is None or d >= n

# ------------------------------------------------------------------------------------------------ 0.0.5
# Todo lo nuevo es OPCIONAL y viene DESACTIVADO: quien actualiza desde la 0.0.4 sigue igual hasta que lo active
# en «Copias». Ajustes (tabla ajustes):
#   copia_auto            '1' = copias automáticas activadas (por defecto: desactivadas)
#   copia_auto_cuando     'cerrar' | 'diaria' | 'ambas'  (por defecto 'cerrar')
#   copia_auto_carpeta    carpeta de destino (por defecto, la misma de las copias manuales)
#   copia_auto_conservar  cuántas copias automáticas se guardan (por defecto 10)
#   copia_no_recordar     '1' = el usuario marcó «No volver a recordar» en el aviso de 7 días
CONSERVAR_PROGRAMADAS = 10
PREFIJO_PROGRAMADA = "ContFactu-auto"
CUANDO = {"cerrar": "al cerrar ContFactu", "diaria": "una vez al día (al abrir)", "ambas": "al cerrar y una vez al día"}

def auto_activada(con):
    from .db import ajuste
    return ajuste(con, "copia_auto") == "1"

def auto_cuando(con):
    from .db import ajuste
    v = ajuste(con, "copia_auto_cuando") or "cerrar"
    return v if v in CUANDO else "cerrar"

def auto_conservar(con):
    from .db import ajuste
    try:
        return min(200, max(1, int(ajuste(con, "copia_auto_conservar", CONSERVAR_PROGRAMADAS))))
    except (TypeError, ValueError):
        return CONSERVAR_PROGRAMADAS

def auto_carpeta(con):
    from .db import ajuste
    return Path(ajuste(con, "copia_auto_carpeta") or ajuste(con, "copia_carpeta") or carpeta_defecto())

def _carpeta_usable(carpeta):
    """True si se puede escribir en la carpeta (un USB quitado o una unidad de red caída devuelven False)."""
    try:
        carpeta = Path(carpeta)
        if not carpeta.is_absolute():
            return False
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / f".contfactu-prueba-{os.getpid()}"
        prueba.write_bytes(b"ok"); prueba.unlink()
        return True
    except OSError:
        return False

def _rotar(carpeta, prefijo, conservar):
    zips = sorted(Path(carpeta).glob(f"{prefijo}-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for viejo in zips[conservar:]:
        try: viejo.unlink()
        except OSError: pass

def copia_programada(con, motivo="cerrar", ahora=None):
    """Copia automática que el usuario ha activado. Si la carpeta elegida no está disponible, la deja en la carpeta
    de copias automáticas de los datos y anota un aviso para la próxima vez que se abra ContFactu.
    Devuelve la ruta del .zip, o None si las copias automáticas están desactivadas o no hay datos."""
    from .db import poner_ajuste, db_path
    if not auto_activada(con) or not db_path().exists() or not con.execute("SELECT 1 FROM empresas").fetchone():
        return None
    destino = auto_carpeta(con)
    aviso = None
    if not _carpeta_usable(destino):
        aviso = (f"La copia automática no se pudo guardar en «{destino}» (¿está conectado el disco o la unidad?). "
                 f"Se ha guardado en «{carpeta_automaticas()}».")
        destino = carpeta_automaticas()
        destino.mkdir(parents=True, exist_ok=True)
    ruta = crear_zip(_nombre_libre(destino, PREFIJO_PROGRAMADA))
    _rotar(destino, PREFIJO_PROGRAMADA, auto_conservar(con))
    with con:
        poner_ajuste(con, "copia_auto_ultima", (ahora or datetime.datetime.now()).isoformat(timespec="seconds"))
        poner_ajuste(con, "copia_auto_ultima_archivo", str(ruta))
        poner_ajuste(con, "copia_auto_aviso", aviso)
    return ruta

def toca_diaria(con, ahora=None):
    """True si está activada la copia diaria y hoy todavía no se ha hecho ninguna automática."""
    from .db import ajuste
    if not auto_activada(con) or auto_cuando(con) not in ("diaria", "ambas"):
        return False
    u = ajuste(con, "copia_auto_ultima")
    return not u or u[:10] != (ahora or datetime.datetime.now()).date().isoformat()

def toca_al_cerrar(con):
    return auto_activada(con) and auto_cuando(con) in ("cerrar", "ambas")

def al_abrir(con, ahora=None):
    """Se llama al arrancar: copia diaria si toca. Nunca lanza excepciones (no debe impedir abrir el programa)."""
    try:
        if toca_diaria(con, ahora):
            return copia_programada(con, "diaria", ahora)
    except Exception:
        pass
    return None

def al_cerrar(con):
    """Se llama al cerrar la ventana: copia si el usuario lo activó. Nunca lanza excepciones."""
    try:
        if toca_al_cerrar(con):
            return copia_programada(con, "cerrar")
    except Exception:
        pass
    return None

def listar_copias(*carpetas):
    """Copias de ContFactu (.zip) en las carpetas indicadas, de la más reciente a la más antigua, sin repetir."""
    vistos, res = set(), []
    for c in carpetas:
        try:
            c = Path(c)
            if not c.is_dir():
                continue
            for p in c.glob("ContFactu-*.zip"):
                k = str(p.resolve()).lower()
                if k in vistos:
                    continue
                vistos.add(k)
                st = p.stat()
                tipo = ("automática" if p.name.startswith(PREFIJO_PROGRAMADA) else
                        "manual" if p.name.startswith("ContFactu-copia") else "de seguridad (actualizar/restaurar)")
                res.append({"nombre": p.name, "ruta": str(p), "carpeta": str(p.parent), "tipo": tipo,
                            "fecha": datetime.datetime.fromtimestamp(st.st_mtime), "tam": st.st_size})
        except OSError:
            continue
    return sorted(res, key=lambda x: x["fecha"], reverse=True)
