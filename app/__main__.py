"""Arranque de ContFactu: servidor local + ventana propia (o navegador si no hay WebView2).

- Pantalla de carga (splash de PyInstaller) que se cierra cuando la ventana está lista.
- Una sola instancia: si ContFactu ya está abierto, trae su ventana al frente (o abre el navegador).
- Al cerrar la ventana se detiene el servidor interno.
- En el .exe (sin consola) los mensajes van a %APPDATA%\\ContFactu\\contfactu.log.
Variables: CONTFACTU_PORT (puerto de la ventana), CONTFACTU_MOVIL_PUERTO (puerto del móvil, si está activado),
CONTFACTU_NO_BROWSER=1 (solo servidor, sin ventana ni navegador), CONTFACTU_NAVEGADOR=1 (forzar el navegador).
"""
import os, socket, sys, threading, time, urllib.request, webbrowser

from . import __version__

PUERTO = 8765
# La ventana solo escucha en este equipo. El acceso móvil, si el usuario lo activa, es otro servidor.
HOST_INTERFAZ = "127.0.0.1"

def config_interfaz(aplicacion, port):
    """Configuración del servidor de la ventana. El host no cambia aunque el móvil esté permitido."""
    import uvicorn
    return uvicorn.Config(aplicacion, host=HOST_INTERFAZ, port=port, log_config=None)

def _parar_movil():
    try:
        from .movil import parar
        parar()
    except Exception as e:
        _log(f"Al cerrar el acceso móvil: {e!r}")

def cerrar_splash():
    try:
        import pyi_splash  # solo existe dentro del .exe con splash
        pyi_splash.close()
    except Exception:
        pass

def es_contfactu(port):
    try:
        with urllib.request.urlopen(f"http://{HOST_INTERFAZ}:{port}/salud", timeout=1) as r:
            return r.read().startswith(b"ContFactu")
    except Exception:
        return False

def traer_al_frente(port):
    try:
        req = urllib.request.Request(f"http://{HOST_INTERFAZ}:{port}/_mostrar", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False

def puerto_libre(desde=PUERTO, intentos=50):
    for p in range(desde, desde + intentos):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST_INTERFAZ, p))
                return p
            except OSError:
                continue
    raise RuntimeError("No hay puertos libres")

def _log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)

def copia_programada(cuando):
    """Copias automáticas de la 0.0.5: no hacen nada si el usuario no las ha activado en «Copias»."""
    try:
        if cuando == "abrir":
            time.sleep(15)   # deja que el programa termine de abrir (y de poner al día la base, si toca)
        from .db import connect
        from . import copias
        con = connect()
        try:
            ruta = copias.al_abrir(con) if cuando == "abrir" else copias.al_cerrar(con)
        finally:
            con.close()
        if ruta:
            _log(f"Copia automática ({cuando}): {ruta}")
    except Exception as e:
        _log(f"Copia automática ({cuando}) no realizada: {e!r}")

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
            webbrowser.open(f"http://{HOST_INTERFAZ}:{base}")
        return
    port = puerto_libre(base)
    url = f"http://{HOST_INTERFAZ}:{port}"
    import uvicorn
    from .main import app, MOSTRAR
    servidor = uvicorn.Server(config_interfaz(app, port))
    _log(f"ContFactu {__version__} en {url}")
    hilo = threading.Thread(target=servidor.run, daemon=True); hilo.start()
    for _ in range(100):
        if servidor.started: break
        time.sleep(0.05)
    try:
        from .movil import sincronizar
        if sincronizar():
            _log("Acceso desde el móvil activo")
    except Exception as e:
        _log(f"Acceso desde el móvil no disponible: {e!r}")
    if solo_servidor:
        cerrar_splash()
        try:
            hilo.join()
        except KeyboardInterrupt:
            servidor.should_exit = True
        finally:
            _parar_movil()
        return
    from .ventana import abrir_ventana, webview2_instalado, limpiar_temporales
    limpiar_temporales()
    threading.Thread(target=copia_programada, args=("abrir",), daemon=True).start()   # solo si el usuario la activó
    usar_ventana = os.environ.get("CONTFACTU_NAVEGADOR") != "1" and webview2_instalado()
    if usar_ventana:
        try:
            abrir_ventana(url, f"ContFactu {__version__}", al_cargar=cerrar_splash,
                          registrar_mostrar=lambda fn: MOSTRAR.__setitem__("fn", fn))
            _log("Ventana cerrada: deteniendo el servidor")
            copia_programada("cerrar")
            _parar_movil()
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
    finally:
        _parar_movil()

if __name__ == "__main__":
    main()
