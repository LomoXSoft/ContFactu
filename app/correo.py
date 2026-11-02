"""Envío de facturas (y demás documentos) por correo electrónico con el PDF adjunto.

- Configuración SMTP por empresa (tabla correo_config): servidor, puerto, seguridad (SSL/TLS, STARTTLS o ninguna),
  usuario, remitente, copia, plantillas de asunto y cuerpo.
- La contraseña NUNCA se guarda en la base de datos: va al Administrador de credenciales de Windows (keyring).
- Nunca se envía nada sin que el usuario pulse «Enviar» en la pantalla de vista previa.
- Cada envío (correcto o fallido) queda registrado en la tabla envios del documento.
"""
import datetime, re, smtplib, ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

SERVICIO = "ContFactu-SMTP"
SEGURIDADES = {"ssl": "SSL/TLS (puerto 465)", "starttls": "STARTTLS (puerto 587)", "ninguna": "Sin cifrar (no recomendado)"}
PUERTOS = {"ssl": 465, "starttls": 587, "ninguna": 25}
ASUNTO_DEFECTO = "{documento} {numero} de {empresa}"
CUERPO_DEFECTO = ("Buenos días:\n\nLe adjuntamos {el_documento} {numero}, de fecha {fecha}, por importe de {total} €.\n\n"
                  "Un saludo,\n{empresa}")
MARCADORES = {
    "numero": "número del documento (p. ej. 26001)", "fecha": "fecha del documento (dd/mm/aaaa)", "total": "total con dos decimales",
    "pendiente": "importe pendiente de cobro", "vencimiento": "primer vencimiento pendiente (dd/mm/aaaa)",
    "cliente": "nombre fiscal del cliente", "empresa": "nombre de su empresa", "documento": "Factura, Presupuesto…",
    "el_documento": "«la factura», «el presupuesto»…",
}
_EMAIL = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+")

class ErrorCorreo(Exception):
    """Error explicable al usuario."""

# ------------------------------------------------------------------------------------------------ contraseña (keyring)
def _keyring():
    import keyring
    import sys
    if sys.platform == "win32":
        try:   # explícito: en el .exe no dependemos del descubrimiento automático de «backends»
            from keyring.backends.Windows import WinVaultKeyring
            if not isinstance(keyring.get_keyring(), WinVaultKeyring):
                keyring.set_keyring(WinVaultKeyring())
        except Exception:
            pass
    return keyring

def _cuenta(eid):
    return f"empresa-{eid}"

def guardar_contrasena(eid, contrasena):
    try:
        kr = _keyring()
        if contrasena:
            kr.set_password(SERVICIO, _cuenta(eid), contrasena)
        else:
            try:
                kr.delete_password(SERVICIO, _cuenta(eid))
            except Exception:
                pass
    except Exception as ex:
        raise ErrorCorreo(f"No he podido guardar la contraseña en el Administrador de credenciales de Windows: {ex}. "
                          "Por seguridad no se guarda en ningún otro sitio.")

def leer_contrasena(eid):
    try:
        return _keyring().get_password(SERVICIO, _cuenta(eid))
    except Exception:
        return None

# ------------------------------------------------------------------------------------------------ configuración
CAMPOS = ("servidor", "puerto", "seguridad", "usuario", "remitente", "nombre_remitente", "copia", "asunto", "cuerpo")

def config(con, eid):
    r = con.execute("SELECT * FROM correo_config WHERE empresa_id=?", (eid,)).fetchone()
    c = dict(r) if r else {"empresa_id": eid, "servidor": "", "puerto": 465, "seguridad": "ssl", "usuario": "", "remitente": "",
                           "nombre_remitente": "", "copia": "", "asunto": ASUNTO_DEFECTO, "cuerpo": CUERPO_DEFECTO}
    c["asunto"] = c.get("asunto") or ASUNTO_DEFECTO
    c["cuerpo"] = c.get("cuerpo") or CUERPO_DEFECTO
    c["configurado"] = bool(r and c.get("servidor") and c.get("remitente"))
    return c

def lista_correos(txt):
    """«a@b.es; c@d.com» -> ['a@b.es', 'c@d.com']. Lanza ErrorCorreo si alguno no es válido."""
    res = []
    for x in re.split(r"[;,]", txt or ""):
        x = x.strip()
        if not x:
            continue
        if not _EMAIL.fullmatch(x):
            raise ErrorCorreo(f"La dirección «{x}» no parece un correo válido.")
        res.append(x)
    return res

def guardar_config(con, eid, datos):
    d = {k: (str(datos.get(k)).strip() if datos.get(k) is not None else "") for k in CAMPOS}
    d["cuerpo"] = (datos.get("cuerpo") or "").replace("\r\n", "\n").strip() or CUERPO_DEFECTO
    d["asunto"] = d["asunto"] or ASUNTO_DEFECTO
    if d["seguridad"] not in SEGURIDADES:
        d["seguridad"] = "ssl"
    try:
        d["puerto"] = int(d["puerto"] or PUERTOS[d["seguridad"]])
        assert 1 <= d["puerto"] <= 65535
    except (ValueError, AssertionError):
        raise ErrorCorreo("El puerto debe ser un número entre 1 y 65535 (normalmente 465 o 587).")
    if d["servidor"] and not re.fullmatch(r"[A-Za-z0-9.-]+", d["servidor"]):
        raise ErrorCorreo(f"El servidor «{d['servidor']}» no es válido (p. ej. smtp.gmail.com).")
    if d["remitente"]:
        lista_correos(d["remitente"])
    lista_correos(d["copia"])
    for campo in ("asunto", "cuerpo"):
        desconocidos = set(re.findall(r"\{(\w+)\}", d[campo])) - set(MARCADORES)
        if desconocidos:
            raise ErrorCorreo(f"Marcador desconocido en el {campo}: " + ", ".join("{" + x + "}" for x in sorted(desconocidos)))
    cols = ["empresa_id", *CAMPOS]
    con.execute(f"INSERT OR REPLACE INTO correo_config({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [eid] + [d[k] for k in CAMPOS])
    return d

# ------------------------------------------------------------------------------------------------ plantillas
def rellenar(plantilla, valores):
    """Sustituye {marcador} por su valor; lo que no sea un marcador conocido se deja tal cual."""
    return re.sub(r"\{(\w+)\}", lambda m: str(valores[m.group(1)]) if m.group(1) in valores else m.group(0), plantilla or "")

def valores_documento(e, d, plazos, titulo, numero):
    from .calc import fmt_eur, dec
    f = lambda s: f"{s[8:10]}/{s[5:7]}/{s[:4]}" if s else ""
    pend = [p for p in plazos if (p.get("tipo") or "") in ("", "A") and dec(p.get("importe")) - dec(p.get("cobrado")) > 0]
    doc = titulo.capitalize() if titulo else "Documento"
    femenino = doc.split()[0].lower() in ("factura",)
    return {"numero": numero, "fecha": f(d.get("fecha")), "total": fmt_eur(d.get("total")), "pendiente": fmt_eur(d.get("pendiente")),
            "vencimiento": f(min(p["fecha"] for p in pend)) if pend and all(p.get("fecha") for p in pend) else f(d.get("fecha")),
            "cliente": d.get("nombre_f") or "", "empresa": e.get("nombre") or "", "documento": doc,
            "el_documento": ("la " if femenino else "el ") + doc.lower()}

def correo_cliente(con, d):
    """Correo del cliente (o proveedor) tomado de su ficha: por código y, si no, por NIF."""
    tabla = "proveedores" if d.get("tipo") == "G" else "clientes"
    r = None
    if d.get("cliente_codigo"):
        r = con.execute(f"SELECT email FROM {tabla} WHERE empresa_id=? AND codigo=?", (d["empresa_id"], d["cliente_codigo"])).fetchone()
    if not (r and r[0]) and d.get("nif"):
        r = con.execute(f"SELECT email FROM {tabla} WHERE empresa_id=? AND REPLACE(UPPER(nif),' ','')=REPLACE(UPPER(?),' ','') "
                        "AND COALESCE(email,'')<>''", (d["empresa_id"], d["nif"])).fetchone()
    return (r[0] or "").strip() if r else ""

# ------------------------------------------------------------------------------------------------ SMTP
def _conectar(c, contrasena, smtp_ssl=None, smtp=None):
    smtp_ssl, smtp = smtp_ssl or smtplib.SMTP_SSL, smtp or smtplib.SMTP
    if not c.get("servidor"):
        raise ErrorCorreo("Falta el servidor de correo saliente (SMTP) en la configuración de correo de la empresa.")
    ctx = ssl.create_default_context()
    try:
        if c["seguridad"] == "ssl":
            s = smtp_ssl(c["servidor"], int(c["puerto"]), timeout=30, context=ctx)
        else:
            s = smtp(c["servidor"], int(c["puerto"]), timeout=30)
            if c["seguridad"] == "starttls":
                s.starttls(context=ctx)
        if c.get("usuario"):
            if not contrasena:
                s.quit()
                raise ErrorCorreo("Falta la contraseña del correo: escríbala en la configuración de correo de la empresa.")
            s.login(c["usuario"], contrasena)
        return s
    except ErrorCorreo:
        raise
    except smtplib.SMTPAuthenticationError:
        raise ErrorCorreo("El servidor ha rechazado el usuario o la contraseña. (Con Gmail u Outlook suele hacer falta una "
                          "«contraseña de aplicación».)")
    except (OSError, smtplib.SMTPException) as ex:
        raise ErrorCorreo(f"No he podido conectar con {c['servidor']}:{c['puerto']} ({SEGURIDADES.get(c['seguridad'])}): {ex}")

def probar(c, contrasena, **fabricas):
    """Conecta, se identifica y se desconecta. No envía nada."""
    s = _conectar(c, contrasena, **fabricas)
    try:
        s.noop()
    finally:
        try: s.quit()
        except Exception: pass
    return True

def construir(c, para, copia, asunto, cuerpo, adjunto_nombre, adjunto):
    if not c.get("remitente"):
        raise ErrorCorreo("Falta la dirección del remitente en la configuración de correo de la empresa.")
    destinos = lista_correos(para)
    if not destinos:
        raise ErrorCorreo("Indique al menos un destinatario.")
    m = EmailMessage()
    m["From"] = formataddr((c.get("nombre_remitente") or "", c["remitente"]))
    m["To"] = ", ".join(destinos)
    cc = lista_correos(copia)
    if cc:
        m["Cc"] = ", ".join(cc)
    m["Subject"] = asunto
    m["Date"] = datetime.datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")
    m["Message-ID"] = make_msgid(domain=c["remitente"].split("@")[-1])
    m.set_content(cuerpo)
    m.add_attachment(adjunto, maintype="application", subtype="pdf", filename=adjunto_nombre)
    return m

def enviar(c, contrasena, mensaje, **fabricas):
    s = _conectar(c, contrasena, **fabricas)
    try:
        rechazados = s.send_message(mensaje)
    except smtplib.SMTPException as ex:
        raise ErrorCorreo(f"El servidor no ha aceptado el mensaje: {ex}")
    finally:
        try: s.quit()
        except Exception: pass
    if rechazados:
        raise ErrorCorreo("El servidor ha rechazado estos destinatarios: " + ", ".join(rechazados))

def registrar(con, did, para, copia, asunto, adjunto, error=None):
    con.execute("INSERT INTO envios(documento_id,fecha_hora,para,copia,asunto,adjunto,resultado,error) VALUES(?,?,?,?,?,?,?,?)",
                (did, datetime.datetime.now().isoformat(timespec="seconds"), para, copia, asunto, adjunto,
                 "error" if error else "enviado", error))

def envios(con, did):
    return [dict(r) for r in con.execute("SELECT * FROM envios WHERE documento_id=? ORDER BY id DESC", (did,))]
