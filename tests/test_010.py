"""0.1.0: la ventana propia no puede colgar el arranque.

pywebview 5+ (la 0.0.5 instala pywebview>=5; en PyPI resuelve 6.2.1) recorre los
atributos públicos del objeto js_api. La 0.0.5 guardaba ahí la ventana. El recorrido
entra en ventana.native (el control WinForms de WebView2) y acaba en
AccessibilityObject.Bounds.Empty, con maximum recursion depth exceeded, y también
en Empty.Location. En Windows eso bloquea el hilo de la interfaz: la página ya
pintada no responde y la pantalla de carga no se cierra, porque el aviso de
«página cargada» se dispara después de ese recorrido.

Aquí no hay ventana real de Windows ni datos reales: el control nativo es un
objeto sintético con la misma forma (cada Empty es un objeto nuevo, así que el
id() de pywebview no corta el ciclo).
"""
import inspect
import logging
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from app.ventana import Puente

RAIZ = Path(__file__).resolve().parent.parent
API = {"abrir", "guardar", "elegir_carpeta", "elegir_zip", "abrir_externo"}


def _get_functions():
    """El get_functions real de la pywebview instalada (está anidado en inject_pywebview)."""
    import webview.util as util
    from webview.util import inject_pywebview
    src = textwrap.dedent(inspect.getsource(inject_pywebview))
    marca = "\n    def generate_func("
    corte = src.find(marca)
    if corte < 0 or "startswith('_')" not in src:
        raise AssertionError("pywebview cambió el recorrido de js_api; hay que revisar el arreglo de _ventana")
    src = src[:corte] + "\n    return get_functions\n"
    src = src.replace("def inject_pywebview(", "def _extraer(", 1)
    ns = dict(util.__dict__)
    ns["Window"] = object
    exec(src, ns, ns)
    return ns["_extraer"]("edgechromium", None)


class _Aviso(logging.Handler):
    def __init__(self):
        super().__init__()
        self.mensajes = []

    def emit(self, record):
        self.mensajes.append(record.getMessage())


def _con_log_de_pywebview():
    lg = logging.getLogger("pywebview")
    aviso = _Aviso()
    previo = (lg.handlers[:], lg.level, lg.propagate)
    lg.handlers = [aviso]
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    return lg, aviso, previo


def _restaurar_log(lg, previo):
    lg.handlers, lg.level, lg.propagate = previo


class _Rect:
    """Imita System.Drawing.Rectangle: Empty devuelve otro objeto cada vez."""

    def __init__(self, cuenta):
        self._cuenta = cuenta

    def __dir__(self):
        return ["Empty", "Location"]

    @property
    def Empty(self):
        self._cuenta[0] += 1
        return _Rect(self._cuenta)

    @property
    def Location(self):
        self._cuenta[0] += 1
        return _Punto(self._cuenta)


class _Punto:
    def __init__(self, cuenta):
        self._cuenta = cuenta

    def __dir__(self):
        return ["X"]

    @property
    def X(self):
        self._cuenta[0] += 1
        raise RuntimeError("Location sintetica")


class _Bounds:
    def __init__(self, cuenta):
        self._cuenta = cuenta

    def __dir__(self):
        return ["Empty", "Location"]

    @property
    def Empty(self):
        self._cuenta[0] += 1
        return _Rect(self._cuenta)

    @property
    def Location(self):
        self._cuenta[0] += 1
        return _Punto(self._cuenta)


class _Accesibilidad:
    def __init__(self, cuenta):
        self._cuenta = cuenta

    def __dir__(self):
        return ["Bounds"]

    @property
    def Bounds(self):
        self._cuenta[0] += 1
        return _Bounds(self._cuenta)


class _Nativo:
    def __init__(self, cuenta):
        self._cuenta = cuenta

    def __dir__(self):
        return ["AccessibilityObject"]

    @property
    def AccessibilityObject(self):
        self._cuenta[0] += 1
        return _Accesibilidad(self._cuenta)


class _VentanaNativa:
    """Sustituto sintético de webview.Window: .native es el control, no un objeto COM."""

    def __init__(self):
        self.cuenta = [0]
        self.dialogos = []

    def __dir__(self):
        return ["native", "create_file_dialog"]

    @property
    def native(self):
        self.cuenta[0] += 1
        return _Nativo(self.cuenta)

    def create_file_dialog(self, tipo, directory="", save_filename="", file_types=()):
        self.dialogos.append((tipo, directory, save_filename, file_types))
        return None


def _publico(obj):
    return {n for n in dir(obj) if not n.startswith("_")}


def test_el_puente_solo_publica_la_api_de_la_pagina(tmp_path):
    p = Puente("http://127.0.0.1:9", carpeta_tmp=str(tmp_path / "tmp"))
    p._ventana = _VentanaNativa()
    assert _publico(p) == API
    assert p._ventana.cuenta[0] == 0


def test_pywebview_revienta_si_la_ventana_es_publica_y_no_si_es_privada():
    """El fallo de la 0.0.5, con el recorrido real de la pywebview instalada."""
    from webview.util import inject_pywebview
    src = inspect.getsource(inject_pywebview)
    # El splash espera a loaded, y loaded se señala después de construir la API.
    assert src.find("func_list = generate_func()") < src.find("loaded.set()")

    nativa = _VentanaNativa()
    rota = Puente("http://127.0.0.1:9")
    rota.ventana = nativa   # así lo hacía la 0.0.5: atributo público
    lg, aviso, previo = _con_log_de_pywebview()
    limite = sys.getrecursionlimit()
    sys.setrecursionlimit(220)
    try:
        funcs = _get_functions()(rota)
    finally:
        sys.setrecursionlimit(limite)
        _restaurar_log(lg, previo)
    texto = "\n".join(aviso.mensajes)
    assert nativa.cuenta[0] > 20
    assert "ventana.native.AccessibilityObject.Bounds.Empty" in texto
    assert "maximum recursion depth exceeded" in texto or "JS_API_MAX_DEPTH" in texto or "Maximum js_api attribute depth" in texto
    assert "Empty.Location" in texto
    assert "ventana.create_file_dialog" in funcs

    buena = Puente("http://127.0.0.1:9")
    buena._ventana = nativa2 = _VentanaNativa()
    lg, aviso, previo = _con_log_de_pywebview()
    try:
        funcs = _get_functions()(buena)
    finally:
        _restaurar_log(lg, previo)
    assert nativa2.cuenta[0] == 0
    assert set(funcs) == API
    assert not any("ventana" in n or "native" in n for n in funcs)
    assert not any("ventana.native" in m for m in aviso.mensajes)
    # La página sigue pudiendo llamar a las mismas acciones, con los mismos argumentos.
    assert funcs["abrir"] == ["ruta"] and funcs["guardar"] == ["ruta"]
    assert funcs["elegir_carpeta"] == ["inicial"] and funcs["elegir_zip"] == []
    assert funcs["abrir_externo"] == ["url"]


def test_inyectar_la_api_dispara_loaded_sin_tocar_el_nativo():
    """Cierre del splash: pywebview señala loaded solo cuando la API ya está expuesta."""
    import webview
    from webview.util import inject_pywebview

    class AvisoCarga:
        def __init__(self):
            self.ev = threading.Event()
            self.handlers = []
            self.veces = 0

        def set(self, *a, **k):
            self.veces += 1
            for fn in list(self.handlers):
                fn(*a, **k)
            self.ev.set()

        def __iadd__(self, fn):
            self.handlers.append(fn)
            return self

    class Eventos:
        def __init__(self):
            self.before_load = AvisoCarga()
            self.loaded = AvisoCarga()
            self._pywebviewready = AvisoCarga()

    nativa = _VentanaNativa()
    puente = Puente("http://127.0.0.1:9")
    puente._ventana = nativa
    splash = []

    class Ventana:
        def __init__(self):
            self._js_api = puente
            self._functions = {}
            self._expose_lock = threading.Lock()
            self.uid = "sintetico"
            self.js_api_endpoint = None
            self.events = Eventos()
            self.text_select = True
            self.zoomable = False
            self.draggable = False
            self.easy_drag = False
            self.frameless = False
            self.state = {}
            self.js = []

        def run_js(self, codigo):
            self.js.append(codigo)

    v = Ventana()
    v.events.loaded += lambda *a: splash.append("cerrado")
    inject_pywebview("edgechromium", v)
    assert v.events.loaded.ev.wait(3), "loaded no llegó: el splash se quedaría delante"
    assert splash == ["cerrado"] and v.events.loaded.veces == 1
    assert nativa.cuenta[0] == 0
    assert len(v.js) >= 2
    api_js = v.js[-1]
    for nombre in API:
        assert f'"func": "{nombre}"' in api_js
    assert "ventana" not in api_js and "native" not in api_js
    assert webview.__name__ == "webview"


def test_abrir_ventana_cierra_el_splash_y_no_guarda_la_ventana_en_publico(tmp_path, monkeypatch):
    import types
    from app.__main__ import cerrar_splash
    from app.ventana import abrir_ventana

    monkeypatch.setenv("CONTFACTU_DATA", str(tmp_path / "datos"))
    monkeypatch.setattr(sys, "platform", "win32")
    cerrados = []
    splash = types.ModuleType("pyi_splash")
    splash.close = lambda: cerrados.append(1)
    monkeypatch.setitem(sys.modules, "pyi_splash", splash)

    class Ev:
        def __init__(self):
            self.handlers = []

        def __iadd__(self, fn):
            self.handlers.append(fn)
            return self

    class V:
        def __init__(self):
            self.events = types.SimpleNamespace(loaded=Ev())
            self.on_top = False

        def restore(self):
            pass

        def show(self):
            pass

    class WV:
        def __init__(self):
            self.arranque = None
            self.v = None
            self.js_api = None

        class FileDialog:
            FOLDER = "carpeta"
            OPEN = "abrir"
            SAVE = "guardar"

        def create_window(self, titulo, url, js_api=None, **kw):
            self.js_api = js_api
            self.v = V()
            self.titulo = titulo
            self.url = url
            self.kw = kw
            return self.v

        def start(self, **kw):
            self.arranque = kw
            for fn in self.v.events.loaded.handlers:
                fn()

    falso = WV()
    monkeypatch.setitem(sys.modules, "webview", falso)
    mostrar = {}
    abrir_ventana("http://127.0.0.1:9", "ContFactu 0.1.0", al_cargar=cerrar_splash,
                  registrar_mostrar=lambda fn: mostrar.__setitem__("fn", fn))
    assert cerrados == [1]
    assert falso.arranque["gui"] == "edgechromium"
    assert falso.arranque["storage_path"].startswith(str(tmp_path / "datos"))
    assert falso.js_api._ventana is falso.v
    assert _publico(falso.js_api) == API
    assert not any(getattr(falso.js_api, n) is falso.v for n in _publico(falso.js_api))
    mostrar["fn"]()   # traer al frente no debe romper si la ventana sintética no hace nada más


def test_dialogos_de_la_api_usan_la_ventana_privada(tmp_path, monkeypatch):
    import urllib.request
    import webbrowser
    v = _VentanaNativa()
    respuestas = [str(tmp_path / "copias"), None, str(tmp_path / "libros.xlsx")]

    def dialogo(tipo, directory="", save_filename="", file_types=()):
        v.dialogos.append((tipo, directory, save_filename, file_types))
        return respuestas.pop(0)

    v.create_file_dialog = dialogo
    p = Puente("http://127.0.0.1:9", carpeta_tmp=str(tmp_path / "tmp"))
    p._ventana = v

    carpeta = p.elegir_carpeta(str(tmp_path))
    assert carpeta == {"ok": True, "ruta": str(tmp_path / "copias")}
    assert p.elegir_zip() == {"ok": False}   # el usuario cancela

    def falso(url, timeout=0):
        class R:
            def read(self):
                return b"PK\x03\x04"
            headers = {"Content-Disposition": 'attachment; filename="libros.xlsx"'}
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        assert url.startswith("http://127.0.0.1:9/")
        return R()

    monkeypatch.setattr(urllib.request, "urlopen", falso)
    guardado = p.guardar("/e/1/libros.xlsx?anio=2026")
    assert guardado["ok"] and guardado["ruta"].endswith("libros.xlsx")
    assert (tmp_path / "libros.xlsx").read_bytes() == b"PK\x03\x04"
    assert len(v.dialogos) == 3
    assert v.cuenta[0] == 0

    abiertos = []
    monkeypatch.setattr(webbrowser, "open", abiertos.append)
    assert p.abrir_externo("https://ejemplo.invalid/ayuda")["ok"] is True
    assert p.abrir_externo("javascript:alert(1)")["ok"] is True
    assert abiertos == ["https://ejemplo.invalid/ayuda"]


def test_la_plantilla_solo_llama_acciones_que_el_puente_expone():
    texto = "\n".join((RAIZ / "app" / "templates" / n).read_text(encoding="utf-8")
                      for n in ("base.html", "copias.html"))
    import re
    usadas = set(re.findall(r"pywebview\.api\.(\w+)", texto))
    assert usadas == API
