# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller para ContFactu (Windows 10/11, 64 bits).
# Uso (desde la carpeta del proyecto):  pyinstaller --noconfirm instalador\ContFactu.spec
# Resultado: dist\ContFactu\ContFactu.exe (+ _internal). NO incluye datos: la base se crea en %APPDATA%\ContFactu.
import os, sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, RAIZ)
ICONO = os.path.join(SPECPATH, "contfactu.ico")

# Versión: único origen en app/__init__.py
_ns = {}
exec(open(os.path.join(RAIZ, "app", "__init__.py"), encoding="utf-8").read(), _ns)
VERSION = _ns["__version__"]
_v = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])

# Pantalla de carga con la versión actual
from herramientas.splash import generar as _generar_splash
SPLASH = _generar_splash(os.path.join(SPECPATH, "splash.png"), ver=VERSION)

# Metadatos del .exe (Propiedades > Detalles). Formato de archivo de versión de PyInstaller.
VERSION_FILE = os.path.join(workpath, "version_info.txt")
os.makedirs(workpath, exist_ok=True)
_cad = lambda k, v: f"StringStruct('{k}', '{v}')"
with open(VERSION_FILE, "w", encoding="utf-8") as _f:
    _f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={_v}, prodvers={_v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('0C0A04B0', [
    {_cad('CompanyName', 'LomoXSoft')}, {_cad('FileDescription', 'ContFactu - facturación')},
    {_cad('FileVersion', VERSION)}, {_cad('InternalName', 'ContFactu')}, {_cad('LegalCopyright', '© LomoXSoft')},
    {_cad('OriginalFilename', 'ContFactu.exe')}, {_cad('ProductName', 'ContFactu')}, {_cad('ProductVersion', VERSION)}])]),
    VarFileInfo([VarStruct('Translation', [0x0C0A, 1200])])])
""")

a = Analysis(
    [os.path.join(SPECPATH, "lanzador.py")],
    pathex=[RAIZ],
    # 7-Zip para poder importar copias .rar de FactuCont sin tener WinRAR instalado
    binaries=[(os.path.join(SPECPATH, "7zip", f), "7zip") for f in ("7z.exe", "7z.dll")],
    # Solo código, plantillas, iconos y licencias. Nunca datos, PDFs de ejemplo ni capturas.
    datas=[(os.path.join(RAIZ, "app", "templates"), os.path.join("app", "templates")),
           (os.path.join(SPECPATH, "7zip", "License.txt"), "7zip"),
           (ICONO, "."), (os.path.join(SPECPATH, "contfactu.png"), ".")] + collect_data_files("webview"),
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("app") + collect_submodules("webview")
                  + ["herramientas", "herramientas.splash", "clr", "openpyxl", "reportlab.graphics.barcode.common",
                     "reportlab.graphics.barcode.code128", "reportlab.graphics.barcode.qr"],
    excludes=["pytest", "PIL.ImageQt", "PyQt5", "PyQt6", "PySide2", "PySide6", "numpy", "gi", "cefpython3"],
    noarchive=False,
)
pyz = PYZ(a.pure)
splash = Splash(SPLASH, binaries=a.binaries, datas=a.datas, text_pos=None, minify_script=True, always_on_top=True)
exe = EXE(
    pyz, a.scripts, splash, [],
    exclude_binaries=True,
    name="ContFactu",
    console=False,            # sin ventana negra; los mensajes van a %APPDATA%\ContFactu\contfactu.log
    icon=ICONO if os.path.exists(ICONO) else None,
    version=VERSION_FILE if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, splash.binaries, strip=False, upx=False, name="ContFactu")
