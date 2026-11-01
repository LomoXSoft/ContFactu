"""Arranque de ContFactu: servidor local + ventana propia (o navegador si no hay WebView2).

- Pantalla de carga (splash de PyInstaller) que se cierra cuando la ventana está lista.
- Una sola instancia: si ContFactu ya está abierto, trae su ventana al frente (o abre el navegador).
- Al cerrar la ventana se detiene el servidor interno.
- En el .exe (sin consola) los mensajes van a %APPDATA%\\ContFactu\\contfactu.log.
Variables: CONTFACTU_PORT (puerto), CONTFACTU_NO_BROWSER=1 (solo servidor, sin ventana ni navegador),
CONTFACTU_NAVEGADOR=1 (forzar el navegador en vez de la ventana).
"""
import os, socket, sys, threading, time, urllib.request, webbrowser

from . import __version__

PUERTO = 8765

def cerrar_splash():
    try:
        import pyi_splash  # solo existe dentro del .exe con splash
        pyi_splash.close()
    except Exception:
        pass

def es_contfactu(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/salud", timeout=1) as r:
            return r.read().startswith(b"ContFactu")
    except Exception:
        return False

def traer_al_frente(port):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/_mostrar", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False

def puerto_libre(desde=PUERTO, intentos=50):
    for p in range(desde, desde + intentos):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("No hay puertos libres")

def _log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)

def main():
    from .db import data_dir
    if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
        d = data_dir(); d.mkdir(parents=True, exist_ok=True)
        log = open(d / "contfactu.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    base = int(os.environ.get("CONTFACTU_PORT", PUERTO))
    solo_servidor = os.environ.get("CONTFACTU_NO_BROWSER") == "1"
    if es_contfactu(base):                       # ya hay una instancia
        cerrar_splash()
        if not solo_servidor and not traer_al_frente(base):
            webbrowser.open(f"http://127.0.0.1:{base}")
        return
    port = puerto_libre(base)
    url = f"http://127.0.0.1:{port}"
    import uvicorn
    from .main import app, MOSTRAR
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    _log(f"ContFactu {__version__} en {url}")
    if solo_servidor:
        cerrar_splash(); servidor.run(); return
    hilo = threading.Thread(target=servidor.run, daemon=True); hilo.start()
    for _ in range(100):
        if servidor.started: break
        time.sleep(0.05)
    from .ventana import abrir_ventana, webview2_instalado, limpiar_temporales
    limpiar_temporales()
    usar_ventana = os.environ.get("CONTFACTU_NAVEGADOR") != "1" and webview2_instalado()
    if usar_ventana:
        try:
            abrir_ventana(url, f"ContFactu {__version__}", al_cargar=cerrar_splash,
                          registrar_mostrar=lambda fn: MOSTRAR.__setitem__("fn", fn))
            _log("Ventana cerrada: deteniendo el servidor")
            servidor.should_exit = True; hilo.join(timeout=5)
            return
        except Exception as e:                   # sin pywebview / WebView2: seguimos con el navegador
            _log(f"No se puede abrir la ventana propia ({e!r}); se usa el navegador")
    cerrar_splash()
    webbrowser.open(url)
    try:
        hilo.join()
    except KeyboardInterrupt:
        servidor.should_exit = True

if __name__ == "__main__":
    main()
