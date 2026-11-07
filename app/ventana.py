"""Ventana propia de ContFactu (pywebview → Edge WebView2 en Windows), con alternativa al navegador.

- Título «ContFactu <versión>», icono propio, 1280×860 redimensionable/maximizable.
- Los PDF (factura, recibos) se abren con el visor predeterminado de Windows (desde ahí se imprimen o guardan).
- Los xlsx/CSV se guardan con el diálogo nativo «Guardar como».
- Al cerrar la ventana se detiene el servidor interno.
"""
import os, re, sys, tempfile, time, urllib.parse, urllib.request, webbrowser

_MODO = {"actual": "navegador"}

def modo_actual():
    return {"ventana": "ventana propia (WebView2)", "navegador": "navegador web"}.get(_MODO["actual"], _MODO["actual"])

def webview2_instalado():
    """True si el runtime Edge WebView2 está instalado (viene con Windows 10 actualizado y Windows 11)."""
    if sys.platform != "win32":
        return True
    try:
        import winreg
    except ImportError:
        return False
    guid = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    claves = [(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
              (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
              (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{guid}")]
    for raiz, ruta in claves:
        try:
            with winreg.OpenKey(raiz, ruta) as k:
                v, _ = winreg.QueryValueEx(k, "pv")
                if v and v != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False

def _nombre_de(cabecera, ruta):
    m = re.search(r'filename="?([^";]+)"?', cabecera or "")
    nombre = m.group(1) if m else os.path.basename(urllib.parse.urlparse(ruta).path) or "documento"
    return re.sub(r'[\\/:*?"<>|]+', "_", nombre)

def abrir_con_sistema(ruta):
    if sys.platform == "win32":
        os.startfile(ruta)  # visor predeterminado (Edge, Acrobat…) — desde ahí se imprime
    elif sys.platform == "darwin":
        import subprocess; subprocess.Popen(["open", ruta])
    else:
        import subprocess; subprocess.Popen(["xdg-open", ruta])

class Puente:
    """API expuesta a la página como window.pywebview.api (solo rutas del servidor local).

    pywebview 5 y posteriores recorren los atributos públicos de este objeto para
    ofrecerlos a JavaScript, y no recorren los que empiezan por «_». La ventana va
    en `_ventana`: si fuera pública, el recorrido entraría en el control nativo de
    WebView2 (`ventana.native.AccessibilityObject.Bounds.Empty`, y también
    `Empty.Location`). En Windows eso deja la interfaz sin responder y la pantalla
    de carga no llega a cerrarse, porque ocurre antes del aviso de página cargada.
    """
    def __init__(self, base, carpeta_tmp=None, abrir=abrir_con_sistema, dialogo=None):
        self._base = base.rstrip("/")
        self._tmp = carpeta_tmp or os.path.join(tempfile.gettempdir(), "ContFactu")
        self._abrir = abrir
        self._dialogo = dialogo   # función(nombre) -> ruta elegida o None
        self._ventana = None

    def _bajar(self, ruta):
        if not ruta.startswith("/"):
            raise ValueError("ruta no válida")
        with urllib.request.urlopen(self._base + ruta, timeout=60) as r:
            return r.read(), _nombre_de(r.headers.get("Content-Disposition"), ruta)

    def abrir(self, ruta):
        try:
            datos, nombre = self._bajar(ruta)
            os.makedirs(self._tmp, exist_ok=True)
            destino = os.path.join(self._tmp, f"{int(time.time()*1000)}_{nombre}")
            with open(destino, "wb") as f:
                f.write(datos)
            self._abrir(destino)
            return {"ok": True, "ruta": destino}
        except Exception as e:
            return {"ok": False, "mensaje": f"No he podido abrir el documento: {e}"}

    def guardar(self, ruta):
        try:
            datos, nombre = self._bajar(ruta)
            destino = self._elegir(nombre)
            if not destino:
                return {"ok": False}
            with open(destino, "wb") as f:
                f.write(datos)
            return {"ok": True, "ruta": destino, "mensaje": f"Guardado en:\n{destino}"}
        except Exception as e:
            return {"ok": False, "mensaje": f"No he podido guardar el archivo: {e}"}

    def elegir_carpeta(self, inicial=""):
        """Diálogo nativo «Seleccionar carpeta» (para la carpeta de las copias de seguridad)."""
        try:
            if self._dialogo:
                r = self._dialogo(None)
            else:
                import webview
                tipo = webview.FileDialog.FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG
                r = self._ventana.create_file_dialog(tipo, directory=inicial if inicial and os.path.isdir(inicial) else "")
            if not r:
                return {"ok": False}
            return {"ok": True, "ruta": r if isinstance(r, str) else r[0]}
        except Exception as e:
            return {"ok": False, "mensaje": f"No he podido abrir el diálogo: {e}"}

    def elegir_zip(self):
        """Diálogo nativo «Abrir» para elegir el .zip de una copia (devuelve la ruta, que el servidor lee directamente)."""
        try:
            if self._dialogo:
                r = self._dialogo("copia.zip")
            else:
                import webview
                tipo = webview.FileDialog.OPEN if hasattr(webview, "FileDialog") else webview.OPEN_DIALOG
                r = self._ventana.create_file_dialog(tipo, file_types=("Copia de ContFactu (*.zip)",))
            if not r:
                return {"ok": False}
            return {"ok": True, "ruta": r if isinstance(r, str) else r[0]}
        except Exception as e:
            return {"ok": False, "mensaje": f"No he podido abrir el diálogo: {e}"}

    def abrir_externo(self, url):
        if url.startswith(("http://", "https://", "mailto:")):
            webbrowser.open(url)
        return {"ok": True}

    def _elegir(self, nombre):
        if self._dialogo:
            return self._dialogo(nombre)
        import webview
        ext = os.path.splitext(nombre)[1].lstrip(".").lower()
        tipos = {"xlsx": ("Libro de Excel (*.xlsx)",), "csv": ("Texto CSV (*.csv)",), "pdf": ("PDF (*.pdf)",)}.get(ext, ("Todos (*.*)",))
        docs = os.path.join(os.path.expanduser("~"), "Documents")
        r = self._ventana.create_file_dialog(webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else webview.SAVE_DIALOG,
                                            directory=docs if os.path.isdir(docs) else "", save_filename=nombre, file_types=tipos)
        if not r:
            return None
        return r if isinstance(r, str) else r[0]

def limpiar_temporales(carpeta=None, dias=2):
    carpeta = carpeta or os.path.join(tempfile.gettempdir(), "ContFactu")
    if not os.path.isdir(carpeta):
        return
    limite = time.time() - dias * 86400
    for n in os.listdir(carpeta):
        p = os.path.join(carpeta, n)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) < limite:
                os.remove(p)
        except OSError:
            pass

def icono():
    for base in (getattr(sys, "_MEIPASS", ""), os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instalador")):
        for n in ("contfactu.ico", "contfactu.png"):
            p = os.path.join(base, n)
            if base and os.path.exists(p):
                return p
    return None

def carpeta_webview():
    """Perfil de WebView2 (caché, ajustes). Va en la carpeta de datos del usuario: el programa puede estar en
    C:\\Program Files, donde no se puede (ni se debe) escribir."""
    from .db import data_dir
    p = data_dir() / "WebView2"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)

def abrir_ventana(url, titulo, al_cargar=None, registrar_mostrar=None):
    """Abre la ventana y BLOQUEA hasta que se cierra. Lanza excepción si pywebview/WebView2 no están disponibles."""
    import webview
    puente = Puente(url)
    v = webview.create_window(titulo, url, js_api=puente, width=1280, height=860, min_size=(900, 600),
                              resizable=True, text_select=True, confirm_close=False)
    puente._ventana = v
    if al_cargar:
        v.events.loaded += lambda *a: al_cargar()
    if registrar_mostrar:
        def mostrar():
            try:
                v.restore(); v.show(); v.on_top = True; v.on_top = False
            except Exception:
                pass
        registrar_mostrar(mostrar)
    _MODO["actual"] = "ventana"
    kw = {"gui": "edgechromium"} if sys.platform == "win32" else {}
    ico = icono()
    kw["storage_path"] = carpeta_webview()   # perfil de WebView2 en %APPDATA%, nunca junto al programa
    try:
        webview.start(private_mode=False, icon=ico, **kw)
    except TypeError:
        webview.start(private_mode=False, **kw)
