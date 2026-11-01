"""Localiza los datos de FactuCont a importar: una carpeta, o un .zip/.rar copiado (p. ej. desde un equipo antiguo o una máquina virtual).
No se asume ninguna ruta: el usuario elige siempre el origen."""
import os, re, shutil, subprocess, sys, tempfile, zipfile

class OrigenError(Exception):
    pass

def _es_empresa(p):
    return os.path.isdir(p) and any(f.lower().endswith(".dbf") for f in os.listdir(p))

def buscar_fc5(raiz, profundidad=5):
    """Devuelve la carpeta que contiene las empresas (00001, 00002...) dentro de `raiz`."""
    raiz = os.path.abspath(raiz)
    for actual, dirs, _ in os.walk(raiz):
        if actual[len(raiz):].count(os.sep) > profundidad:
            dirs[:] = []; continue
        if any(re.fullmatch(r"\d{5}", d) and _es_empresa(os.path.join(actual, d)) for d in dirs):
            return actual
    raise OrigenError("No encuentro datos de FactuCont ahí: debe haber carpetas de empresa (00001, 00002…) con archivos .dbf.")

def _7zip_incluido():
    """7-Zip (7z.exe + 7z.dll, licencia LGPL + restricción unRAR) que va dentro del instalador: lee .rar sin WinRAR."""
    bases = [getattr(sys, "_MEIPASS", ""), os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instalador")]
    return [os.path.join(b, "7zip", "7z.exe") for b in bases if b]

def _extractores_rar():
    win = os.environ.get("SystemRoot", r"C:\Windows")
    pf = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    c = [] if sys.platform != "win32" else _7zip_incluido() + [os.path.join(win, "System32", "tar.exe")]           # bsdtar de Windows 10/11 (lee RAR)
    for b in filter(None, pf):
        c += [os.path.join(b, "7-Zip", "7z.exe"), os.path.join(b, "WinRAR", "UnRAR.exe")]
    c += [shutil.which(x) for x in ("7zz", "7z", "bsdtar", "unrar")]
    return [x for x in c if x and os.path.isfile(x)]

def _sin_ventana():
    return {"creationflags": 0x08000000} if sys.platform == "win32" else {}

def extraer(archivo, destino):
    low = archivo.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(archivo) as z:
            for n in z.namelist():   # protección contra rutas fuera del destino
                if os.path.isabs(n) or ".." in n.replace("\\", "/").split("/"):
                    raise OrigenError("El .zip contiene rutas no válidas.")
            z.extractall(destino)
        return
    if low.endswith(".rar"):
        for exe in _extractores_rar():
            n = os.path.basename(exe).lower()
            args = ([exe, "x", "-y", "-bso0", "-bsp0", f"-o{destino}", archivo] if n in ("7z.exe", "7z", "7zz") else
                    [exe, "x", "-o+", archivo, destino + os.sep] if n.startswith("unrar") else
                    [exe, "-xf", archivo, "-C", destino])
            r = subprocess.run(args, capture_output=True, **_sin_ventana())
            if r.returncode == 0:
                return
        raise OrigenError("No he podido abrir el .rar. Descomprímalo con WinRAR o 7-Zip y elija la carpeta resultante, "
                          "o comprímalo como .zip.")
    raise OrigenError("Solo se admiten carpetas, .zip o .rar.")

def preparar(ruta):
    """Devuelve (carpeta_fc5, carpeta_temporal_o_None). Si es un archivo comprimido lo extrae a un temporal."""
    ruta = (ruta or "").strip().strip('"')
    if not ruta:
        raise OrigenError("Indique la carpeta o el archivo .zip/.rar con los datos de FactuCont.")
    if os.path.isdir(ruta):
        return buscar_fc5(ruta), None
    if os.path.isfile(ruta):
        tmp = tempfile.mkdtemp(prefix="contfactu_imp_")
        try:
            extraer(ruta, tmp)
            return buscar_fc5(tmp), tmp
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True); raise
    raise OrigenError(f"No encuentro «{ruta}».")
