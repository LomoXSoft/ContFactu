"""Acceso opcional desde un móvil emparejado (ContFactu 0.2.0).

Los datos siguen en este PC. Con la opción desactivada (el valor de origen) no se
abre ningún puerto nuevo: la ventana sigue en 127.0.0.1 y esta módulo no escucha.

Con la opción activada se abre un segundo servidor, solo con la API del móvil, en
todas las interfaces (wifi y VPN) y solo por TLS. El certificado es autofirmado;
su huella SHA-256 va en el código QR para que la aplicación la ancle y rechace
cualquier otro certificado. El token de cada dispositivo se guarda solo como
hash SHA-256. El código de emparejamiento caduca, es de un solo uso y se bloquea
tras varios fallos.

Nada de esto se cuelga del puente de pywebview: ese objeto no debe tener estado
nativo en atributos públicos.
"""
import datetime, hashlib, hmac, json, os, socket, ssl, sys, threading, time
import secrets

HOST_MOVIL = "0.0.0.0"          # wifi, WireGuard y Tailscale, sin abrir el router
PUERTO = 8766
CADUCIDAD_SEGUNDOS = 10 * 60
MAX_FALLOS = 5
BLOQUEO_SEGUNDOS = 15 * 60
MAX_DISPOSITIVOS = 20
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sin 0/O/1/I, para poder dictarlo
_NINGUNO = "0" * 64
_IGNORAR_INTERFAZ = ("docker", "br-", "veth", "virbr", "vmnet", "vboxnet")

class ErrorMovil(Exception):
    """Error explicable en la pantalla de ajustes."""

class CodigoRechazado(Exception):
    """Código de emparejamiento incorrecto o caducado. El mensaje al móvil es siempre el mismo."""

class EmparejamientoBloqueado(Exception):
    def __init__(self, segundos):
        self.segundos = max(1, int(segundos))
        super().__init__("emparejamiento bloqueado")

_lock = threading.Lock()
_estado = {"server": None, "hilo": None, "sock": None, "enlace": None}


def _conectar():
    from . import db
    return db.connect()

def _ajuste(con, clave, defecto=None):
    r = con.execute("SELECT valor FROM ajustes WHERE clave=?", (clave,)).fetchone()
    if not r or r[0] is None:
        return defecto
    return r[0]

def _poner(con, clave, valor):
    con.execute("INSERT OR REPLACE INTO ajustes(clave, valor) VALUES(?, ?)",
                (clave, None if valor is None else str(valor)))

def activado(con):
    """True solo si el usuario marcó la opción. Si la clave no existe, está desactivada."""
    return _ajuste(con, "movil_activo") == "1"

def puerto():
    try:
        n = int(os.environ.get("CONTFACTU_MOVIL_PUERTO") or PUERTO)
        if 1 <= n <= 65535:
            return n
    except (TypeError, ValueError):
        pass
    return PUERTO

def _rutas_cert():
    from .db import data_dir
    base = data_dir() / "movil"
    return base / "cert.pem", base / "clave.pem"

def _proteger(ruta):
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass

def huella_de_der(der):
    """Huella canónica: sha256: + 64 hex minúsculas del certificado en DER (no del PEM ni de la clave)."""
    return "sha256:" + hashlib.sha256(der).hexdigest()

def huella_de_cert(pem):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    cert = x509.load_pem_x509_certificate(pem)
    return huella_de_der(cert.public_bytes(serialization.Encoding.DER))

def _hex_huella(valor):
    x = (valor or "").strip().lower().replace(" ", "")
    if x.startswith("sha256:"):
        x = x[7:]
    x = x.replace(":", "")
    if len(x) != 64 or any(c not in "0123456789abcdef" for c in x):
        return None
    return x

def huellas_iguales(a, b):
    """Compara dos huellas (con o sin «sha256:» y con o sin dos puntos) en tiempo constante."""
    na, nb = _hex_huella(a), _hex_huella(b)
    if not na or not nb:
        return False
    return hmac.compare_digest(na, nb)

def huella():
    """Huella del certificado actual, o None si todavía no se ha creado. No crea archivos."""
    cert, _clave = _rutas_cert()
    if not cert.is_file():
        return None
    return huella_de_cert(cert.read_bytes())

def asegurar_certificado():
    """Crea el certificado autofirmado la primera vez. Si ya existe, no lo cambia: la huella del QR seguiría valiendo."""
    cert_path, clave_path = _rutas_cert()
    if cert_path.is_file() and clave_path.is_file():
        _proteger(clave_path)
        return cert_path, clave_path
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ContFactu")])
    ahora = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(nombre).issuer_name(nombre)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(ahora - datetime.timedelta(minutes=5))
            .not_valid_after(ahora + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("contfactu.local")]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    clave_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    _proteger(clave_path)
    return cert_path, clave_path

# ------------------------------------------------------------------------------------------------ red
def _ignorar_interfaz(nombre):
    n = (nombre or "").lower()
    return n == "lo" or n.startswith(_IGNORAR_INTERFAZ)

def _interfaces_ioctl():
    import fcntl, struct
    SIOCGIFADDR = 0x8915
    res = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _i, nombre in socket.if_nameindex():
            try:
                datos = fcntl.ioctl(s.fileno(), SIOCGIFADDR, struct.pack("256s", nombre.encode()[:15]))
                res.append((nombre, socket.inet_ntoa(datos[20:24])))
            except OSError:
                continue
    finally:
        s.close()
    return res

def _interfaces_hostname():
    res = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            res.append(("", info[4][0]))
    except socket.gaierror:
        pass
    return res

def _interfaces_windows():
    import subprocess
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object { $_.InterfaceAlias + \"`t\" + $_.IPAddress }"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8, creationflags=0x08000000)
    except (OSError, subprocess.TimeoutExpired):
        return _interfaces_hostname()
    if r.returncode != 0 or not r.stdout.strip():
        return _interfaces_hostname()
    res = []
    for linea in r.stdout.splitlines():
        if "\t" not in linea:
            continue
        nombre, ip = linea.split("\t", 1)
        res.append((nombre.strip(), ip.strip()))
    return res or _interfaces_hostname()

def _interfaces():
    if sys.platform == "win32":
        return _interfaces_windows()
    try:
        return _interfaces_ioctl()
    except Exception:
        return _interfaces_hostname()

def clasificar(pares):
    """[(interfaz, ip), ...] -> direcciones útiles para el QR, sin loopback ni puentes de Docker.

    Orden: red local, WireGuard, Tailscale. La aplicación puede probarlas en ese orden.
    Tailscale usa 100.64.0.0/10. WireGuard se reconoce por el nombre de la interfaz (wg*, WireGuard).
    """
    import ipaddress
    vistos, res = set(), []
    for nombre, ip in pares:
        if _ignorar_interfaz(nombre):
            continue
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not isinstance(addr, ipaddress.IPv4Address):
            continue
        if addr.is_loopback or addr.is_link_local or addr.is_unspecified or addr.is_multicast:
            continue
        if ip in vistos:
            continue
        n = (nombre or "").lower()
        if addr in ipaddress.ip_network("100.64.0.0/10") or "tailscale" in n:
            tipo, etiqueta = "tailscale", "Tailscale"
        elif n.startswith("wg") or "wireguard" in n:
            tipo, etiqueta = "wireguard", "WireGuard"
        else:
            tipo, etiqueta = "local", "Wi-Fi o red local"
        vistos.add(ip)
        res.append({"ip": ip, "interfaz": nombre or "", "tipo": tipo, "etiqueta": etiqueta})
    orden = {"local": 0, "wireguard": 1, "tailscale": 2}
    res.sort(key=lambda d: (orden.get(d["tipo"], 9), d["ip"]))
    return res

def direcciones():
    return clasificar(_interfaces())

# ------------------------------------------------------------------------------------------------ emparejamiento
def _normalizar_codigo(codigo):
    return "".join(ch for ch in (codigo or "").upper() if ch.isalnum())

def _hash_codigo(codigo):
    return hashlib.sha256(_normalizar_codigo(codigo).encode("utf-8")).hexdigest()

def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def _limpiar_nombre(nombre):
    limpio = "".join(ch for ch in (nombre or "").strip() if ch.isprintable())
    limpio = limpio[:60].strip()
    return limpio or "Dispositivo móvil"

def segundos_bloqueo(con):
    """Segundos que faltan de bloqueo, o 0. Si el plazo ya pasó, lo levanta."""
    hasta = _ajuste(con, "movil_bloqueo_hasta")
    if not hasta:
        return 0
    try:
        falta = int((datetime.datetime.fromisoformat(hasta) - datetime.datetime.now()).total_seconds())
    except ValueError:
        return 0
    if falta <= 0:
        with con:
            _poner(con, "movil_bloqueo_hasta", None)
            _poner(con, "movil_fallos", "0")
        return 0
    return falta

def _caducado(con):
    exp = _ajuste(con, "movil_codigo_expira")
    if not exp:
        return True
    try:
        return datetime.datetime.now() >= datetime.datetime.fromisoformat(exp)
    except ValueError:
        return True

def _registrar_fallo(con):
    try:
        n = int(_ajuste(con, "movil_fallos") or "0") + 1
    except ValueError:
        n = 1
    with con:
        _poner(con, "movil_fallos", str(n))
        if n >= MAX_FALLOS:
            hasta = datetime.datetime.now() + datetime.timedelta(seconds=BLOQUEO_SEGUNDOS)
            _poner(con, "movil_bloqueo_hasta", hasta.isoformat(timespec="seconds"))

def nuevo_codigo(con):
    """Genera un código de un solo uso y guarda solo su hash. Devuelve el texto visible (XXXX-XXXX) y la caducidad."""
    if not activado(con):
        raise ErrorMovil("El acceso desde el móvil está desactivado.")
    if segundos_bloqueo(con):
        raise ErrorMovil("El emparejamiento está bloqueado un momento. Puede desbloquearlo en este equipo.")
    crudo = "".join(secrets.choice(ALFABETO) for _ in range(8))
    visible = f"{crudo[:4]}-{crudo[4:]}"
    expira = datetime.datetime.now() + datetime.timedelta(seconds=CADUCIDAD_SEGUNDOS)
    with con:
        _poner(con, "movil_codigo_hash", _hash_codigo(visible))
        _poner(con, "movil_codigo_expira", expira.isoformat(timespec="seconds"))
    return {"codigo": visible, "expira": expira}

def emparejar(con, codigo, nombre):
    """Canjea el código por un token. El token sale una sola vez; aquí se guarda su hash."""
    if not activado(con):
        raise ErrorMovil("El acceso desde el móvil está desactivado.")
    seg = segundos_bloqueo(con)
    if seg:
        raise EmparejamientoBloqueado(seg)
    guardado = _ajuste(con, "movil_codigo_hash")
    esperado = guardado if guardado and len(guardado) == 64 else _NINGUNO
    calculado = _hash_codigo(codigo or "")
    vale = hmac.compare_digest(calculado, esperado) and bool(guardado) and not _caducado(con)
    if not vale:
        _registrar_fallo(con)
        seg = segundos_bloqueo(con)
        if seg:
            raise EmparejamientoBloqueado(seg)
        raise CodigoRechazado()
    n = con.execute("SELECT COUNT(*) FROM dispositivos_movil").fetchone()[0]
    if n >= MAX_DISPOSITIVOS:
        raise ErrorMovil("Hay demasiados dispositivos emparejados. Revocar uno antes de añadir otro.")
    token = secrets.token_urlsafe(32)
    nombre = _limpiar_nombre(nombre)
    ahora = datetime.datetime.now().isoformat(timespec="seconds")
    with con:
        _poner(con, "movil_codigo_hash", None)
        _poner(con, "movil_codigo_expira", None)
        _poner(con, "movil_fallos", "0")
        cur = con.execute("INSERT INTO dispositivos_movil(nombre, token_hash, creado, ultimo_acceso) VALUES(?,?,?,?)",
                          (nombre, _hash_token(token), ahora, ahora))
    return {"token": token, "dispositivo_id": cur.lastrowid, "nombre": nombre}

def desbloquear(con):
    with con:
        _poner(con, "movil_fallos", "0")
        _poner(con, "movil_bloqueo_hasta", None)

def bloqueo_hasta(con):
    """Hora límite del bloqueo (ISO) si sigue vigente, o None."""
    if not segundos_bloqueo(con):
        return None
    return _ajuste(con, "movil_bloqueo_hasta")

def dispositivo_por_token(con, token):
    if not token or not isinstance(token, str) or len(token) < 20 or len(token) > 200:
        return None
    r = con.execute("SELECT id, nombre, creado, ultimo_acceso FROM dispositivos_movil WHERE token_hash=?",
                    (_hash_token(token),)).fetchone()
    return dict(r) if r else None

def tocar(con, did):
    ahora = datetime.datetime.now().isoformat(timespec="seconds")
    with con:
        con.execute("UPDATE dispositivos_movil SET ultimo_acceso=? WHERE id=?", (ahora, did))

def listar(con):
    return [dict(r) for r in con.execute(
        "SELECT id, nombre, creado, ultimo_acceso FROM dispositivos_movil ORDER BY id")]

def revocar(con, did):
    with con:
        con.execute("DELETE FROM dispositivos_movil WHERE id=?", (int(did),))

# ------------------------------------------------------------------------------------------------ QR
def payload_qr(codigo, hosts, puerto_n, huella_cert):
    return {"v": 1, "app": "ContFactu", "hosts": list(hosts), "puerto": int(puerto_n),
            "codigo": codigo, "huella": huella_cert}

def payload_json(payload):
    """JSON compacto y estable. El orden de las claves no forma parte del contrato: hay que interpretarlo como JSON."""
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

def qr_svg(texto):
    """SVG del QR (nivel M). None si no se puede generar: el código de respaldo sigue en pantalla."""
    try:
        from reportlab.graphics.barcode.qr import QrCodeWidget
        q = QrCodeWidget(texto, barLevel="M")
        q.qr.make()
        modulos = q.qr.modules
    except Exception:
        return None
    if not modulos:
        return None
    n = len(modulos)
    modulo, margen = 4, 2
    lado = (n + margen * 2) * modulo
    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lado} {lado}" width="220" height="220" '
              f'role="img" aria-label="Código QR de emparejamiento">',
              f'<rect width="{lado}" height="{lado}" fill="#ffffff"/>']
    for y, fila in enumerate(modulos):
        x = 0
        fila = [bool(c) for c in fila]
        while x < n:
            if not fila[x]:
                x += 1
                continue
            x0 = x
            while x < n and fila[x]:
                x += 1
            partes.append(f'<rect x="{(x0 + margen) * modulo}" y="{(y + margen) * modulo}" '
                          f'width="{(x - x0) * modulo}" height="{modulo}" fill="#000000"/>')
    partes.append("</svg>")
    return "".join(partes)

# ------------------------------------------------------------------------------------------------ servidor TLS
def _fabrica_ssl():
    def fabrica(_config, por_defecto):
        ctx = por_defecto()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx
    return fabrica

def en_marcha():
    with _lock:
        servidor = _estado.get("server")
        hilo = _estado.get("hilo")
        return bool(servidor and servidor.started and not servidor.should_exit and hilo and hilo.is_alive())

def enlace():
    """('0.0.0.0', puerto) si el servidor móvil está escuchando; None si no."""
    with _lock:
        if not (_estado.get("server") and _estado["server"].started and not _estado["server"].should_exit):
            return None
        return _estado.get("enlace")

def _esperar(servidor, hilo):
    for _ in range(100):
        if servidor.started:
            return True
        if not hilo.is_alive():
            return False
        time.sleep(0.05)
    return bool(servidor.started)

def _parar_dentro():
    servidor, hilo, sock = _estado.get("server"), _estado.get("hilo"), _estado.get("sock")
    if servidor is not None:
        servidor.should_exit = True
    if hilo is not None and hilo.is_alive():
        hilo.join(timeout=5)
        if hilo.is_alive() and servidor is not None:
            servidor.force_exit = True
            hilo.join(timeout=2)
    if sock is not None:
        try:
            sock.close()
        except OSError:
            pass
    _estado.update(server=None, hilo=None, sock=None, enlace=None)

def parar():
    with _lock:
        _parar_dentro()

def arrancar():
    """Abre el servidor TLS en todas las interfaces. No llama a sys.exit si el puerto está ocupado."""
    with _lock:
        servidor = _estado.get("server")
        hilo = _estado.get("hilo")
        if servidor and servidor.started and not servidor.should_exit and hilo and hilo.is_alive():
            return _estado.get("enlace")
        _parar_dentro()
        cert, clave = asegurar_certificado()
        port = puerto()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.set_inheritable(False)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((HOST_MOVIL, port))
            sock.listen(128)
            sock.setblocking(False)
        except OSError as ex:
            sock.close()
            raise ErrorMovil(f"No se ha podido abrir el puerto {port} para el móvil. Si está ocupado, cierre el otro "
                             "programa o indique otro con la variable CONTFACTU_MOVIL_PUERTO.") from ex
        import uvicorn
        from .api_movil import aplicacion
        config = uvicorn.Config(aplicacion, host=HOST_MOVIL, port=port, log_config=None, access_log=False,
                                log_level="warning", server_header=False, timeout_graceful_shutdown=2,
                                ssl_certfile=str(cert), ssl_keyfile=str(clave), ssl_context_factory=_fabrica_ssl())
        servidor = uvicorn.Server(config)
        fallo = []

        def _run():
            try:
                servidor.run(sockets=[sock])
            except BaseException as ex:  # SystemExit incluido: un fallo de uvicorn no puede cerrar ContFactu
                fallo.append(ex)

        hilo = threading.Thread(target=_run, name="contfactu-movil", daemon=True)
        _estado.update(server=servidor, hilo=hilo, sock=sock, enlace=sock.getsockname())
        hilo.start()
        if not _esperar(servidor, hilo):
            _parar_dentro()
            raise ErrorMovil(f"No se ha podido abrir el acceso desde el móvil en el puerto {port}.")
        return _estado.get("enlace")

def activar(con):
    """Marca la opción y abre el puerto. El certificado se crea aquí, no al abrir la pantalla."""
    asegurar_certificado()
    with con:
        _poner(con, "movil_activo", "1")
    if not en_marcha():
        arrancar()

def desactivar(con):
    with con:
        _poner(con, "movil_activo", "0")
    parar()

def sincronizar():
    """Deja el puerto como diga el ajuste. Desactivado: no escucha. Lo usa el arranque y una restauración."""
    con = _conectar()
    try:
        on = activado(con)
    finally:
        con.close()
    if not on:
        parar()
        return False
    if not en_marcha():
        arrancar()
    return en_marcha()
