"""Punto de entrada del ejecutable ContFactu.exe."""
import sys

def _salida_autoprueba():
    """El .exe no tiene consola: el fallo de la autoprueba queda en %TEMP%, nunca en %APPDATA%."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    import os, tempfile
    log = open(os.path.join(tempfile.gettempdir(), "contfactu-autoprueba-qr.log"), "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log

def autoprueba_qr():
    """Genera un PNG de QR y sale. No arranca servidores, no escucha y no toca datos."""
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass
    _salida_autoprueba()
    from app.movil import autoprueba_qr as generar
    return generar()

if __name__ == "__main__":
    if "--autoprueba-qr" in sys.argv:
        try:
            sys.exit(autoprueba_qr())
        except Exception:
            import traceback
            traceback.print_exc()
            sys.exit(1)
    from app.__main__ import main
    main()
