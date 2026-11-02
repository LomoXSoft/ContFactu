"""Altas desde cero: empresas nuevas (sin FactuCont), clientes y proveedores.
Como en repo.py, las funciones reciben una conexión y NO hacen commit."""
import re
from .repo import ErrorNegocio, hoy, RE_DEFECTO, parse_tasas_re
from .calc import tipo_iva_valido

IVAS_DEFECTO = "21,10,4,0"
CAMPOS_EMPRESA = ("codigo", "nombre", "nif", "direccion", "cp", "ciudad", "provincia", "telefono", "email", "actividad",
                  "ccc", "bic", "serie_defecto", "contador_inicial", "ivas", "re_tasas")
CAMPOS_TERCERO = {
    "clientes": ("codigo", "nombre", "nombre_f", "nif", "direccion", "ciudad", "telefono", "movil", "email", "contacto",
                 "forma_pago", "dias_pago", "descuento", "recargo", "ccc", "bic", "domiciliacion"),
    "proveedores": ("codigo", "nombre", "nombre_f", "nif", "direccion", "ciudad", "telefono", "movil", "email", "contacto",
                    "forma_pago", "dias_pago", "retencion"),
}

# ------------------------------------------------------------------------------------------------- NIF / CIF / NIE
_LETRAS = "TRWAGMYFPDXBNJZSQVHLCKE"

def nif_valido(nif):
    """Comprueba el dígito/letra de control de un NIF (DNI), NIE o CIF español. Acepta guiones y espacios."""
    n = re.sub(r"[\s.\-]", "", (nif or "").upper())
    if n.startswith("ES"):
        n = n[2:]
    if re.fullmatch(r"\d{8}[A-Z]", n):
        return _LETRAS[int(n[:8]) % 23] == n[8]
    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", n):
        return _LETRAS[int("XYZ".index(n[0]).__str__() + n[1:8]) % 23] == n[8]
    if re.fullmatch(r"[KLM]\d{7}[A-Z]", n):
        return _LETRAS[int(n[1:8]) % 23] == n[8]
    if re.fullmatch(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]", n):
        dig = n[1:8]
        pares = sum(int(dig[i]) for i in (1, 3, 5))
        impares = sum(sum(divmod(2 * int(dig[i]), 10)) for i in (0, 2, 4, 6))
        c = (10 - (pares + impares) % 10) % 10
        if n[0] in "PQRSNW":
            return n[8] == "JABCDEFGHI"[c]
        if n[0] in "ABEH":
            return n[8] == str(c)
        return n[8] in (str(c), "JABCDEFGHI"[c])
    return False

def normalizar_nif(nif):
    return re.sub(r"[\s.\-]", "", (nif or "").upper())

# ------------------------------------------------------------------------------------------------- empresas
def siguiente_codigo_empresa(con):
    usados = {r[0] for r in con.execute("SELECT codigo FROM empresas")}
    n = 1
    while f"{n:05d}" in usados:
        n += 1
    return f"{n:05d}"

def ivas_de(e):
    """Tipos de IVA habituales de la empresa (texto con punto decimal, p. ej. '7.5'); el primero es el de por defecto."""
    return [x.strip() for x in ((e or {}).get("ivas") or IVAS_DEFECTO).split(",") if x.strip()]

def tasas_re_de(e):
    """{'21': '5.2', ...} recargo de equivalencia por tipo de IVA de la empresa."""
    txt = (e or {}).get("re_tasas")
    try:
        return {format(k, "f"): format(v, "f") for k, v in parse_tasas_re(RE_DEFECTO if txt is None else txt).items()}
    except ValueError:
        return {format(k, "f"): format(v, "f") for k, v in parse_tasas_re(RE_DEFECTO).items()}

def tabla_tipos(e):
    """Filas (iva, re) para la tabla editable de tipos de la ficha de la empresa: los habituales y los que tengan recargo."""
    re_ = tasas_re_de(e)
    filas = [(i, re_.get(i, "")) for i in ivas_de(e)]
    filas += [(i, r) for i, r in re_.items() if i not in ivas_de(e)]
    return filas

def tipos_desde_tabla(ivas, res):
    """Listas paralelas del formulario (tipo de IVA, recargo) -> ('21,10,7.5', '21:5.2,10:1.4'). Filas vacías se ignoran."""
    lista, tasas = [], []
    for iva, re_ in zip(ivas, res):
        iva, re_ = (iva or "").strip(), (re_ or "").strip()
        if not iva and not re_:
            continue
        if not iva:
            raise ErrorNegocio(f"Hay un recargo ({re_}) sin tipo de IVA.")
        try:
            iva = tipo_iva_valido(iva)
            re_ = tipo_iva_valido(re_) if re_ else ""
        except ValueError as ex:
            raise ErrorNegocio(str(ex))
        if iva in lista:
            raise ErrorNegocio(f"El tipo de IVA {iva.replace('.', ',')} % está repetido.")
        lista.append(iva)
        if re_ and re_ != "0":
            tasas.append(f"{iva}:{re_}")
    if not lista:
        raise ErrorNegocio("Indique al menos un tipo de IVA.")
    return ",".join(lista), ",".join(tasas)

def _limpiar_empresa(datos, con, eid=None):
    d = {k: (str(datos.get(k)).strip() if datos.get(k) is not None else "") for k in CAMPOS_EMPRESA}
    if not d["nombre"]:
        raise ErrorNegocio("Falta el nombre o razón social de la empresa.")
    if not d["nif"]:
        raise ErrorNegocio("Falta el NIF/CIF de la empresa: es obligatorio en las facturas.")
    d["nif"] = normalizar_nif(d["nif"])
    if not nif_valido(d["nif"]):
        raise ErrorNegocio(f"El NIF/CIF «{d['nif']}» no es válido (revise la letra o el dígito de control).")
    d["codigo"] = d["codigo"] or siguiente_codigo_empresa(con)
    if not re.fullmatch(r"\d{1,5}", d["codigo"]):
        raise ErrorNegocio("El código de empresa debe ser numérico, de hasta 5 cifras (p. ej. 00001).")
    d["codigo"] = d["codigo"].zfill(5)
    otra = con.execute("SELECT id, nombre FROM empresas WHERE codigo=?", (d["codigo"],)).fetchone()
    if otra and otra[0] != eid:
        raise ErrorNegocio(f"El código {d['codigo']} ya lo usa la empresa «{otra[1]}». Elija otro.")
    if d["cp"] and not re.fullmatch(r"\d{5}", d["cp"]):
        raise ErrorNegocio("El código postal debe tener 5 cifras.")
    if d["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", d["email"]):
        raise ErrorNegocio(f"El correo electrónico «{d['email']}» no parece válido.")
    d["serie_defecto"] = d["serie_defecto"].upper()[:3]
    if d["serie_defecto"] and not re.fullmatch(r"[A-Z0-9]{1,3}", d["serie_defecto"]):
        raise ErrorNegocio("La serie solo puede tener letras y números (máximo 3).")
    if d["serie_defecto"] == "R":
        raise ErrorNegocio("La serie R está reservada para las facturas rectificativas.")
    try:
        d["contador_inicial"] = int(d["contador_inicial"] or 1)
        assert 1 <= d["contador_inicial"] <= 99999
    except (ValueError, AssertionError):
        raise ErrorNegocio("El primer número de factura debe ser un número entre 1 y 99999.")
    ivas = []
    for x in (d["ivas"] or IVAS_DEFECTO).replace(";", ",").split(","):
        if not x.strip():
            continue
        try:
            x = tipo_iva_valido(x)
        except ValueError as ex:
            raise ErrorNegocio(f"Tipo de IVA no válido: «{x.strip()}». {ex}")
        if x not in ivas:
            ivas.append(x)
    if not ivas:
        raise ErrorNegocio("Indique al menos un tipo de IVA.")
    if datos.get("re_tasas") is None:
        d["re_tasas"] = RE_DEFECTO if eid is None else None
    else:
        try:
            parse_tasas_re(d["re_tasas"])
        except ValueError as ex:
            raise ErrorNegocio(str(ex))
    d["ivas"] = ",".join(ivas)
    return d

def crear_empresa(con, datos):
    """Empresa vacía lista para trabajar (sin FactuCont). Devuelve el id."""
    d = _limpiar_empresa(datos, con)
    cols = list(d) + ["origen", "creada"]
    cur = con.execute(f"INSERT INTO empresas({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                      [d[k] for k in d] + ["nuevo", hoy()])
    return cur.lastrowid

def actualizar_empresa(con, eid, datos):
    d = _limpiar_empresa(datos, con, eid)
    if d.get("re_tasas") is None:
        d.pop("re_tasas")   # el formulario no lo envió: se conserva el que hubiera
    if con.execute("SELECT 1 FROM documentos WHERE empresa_id=? AND tipo='F'", (eid,)).fetchone():
        d.pop("contador_inicial")   # con facturas emitidas ya no cambia el arranque de la numeración
    con.execute(f"UPDATE empresas SET {', '.join(k + '=?' for k in d)} WHERE id=?", [*d.values(), eid])

def poner_logo(con, eid, nombre_archivo):
    con.execute("UPDATE empresas SET logo=? WHERE id=?", (nombre_archivo, eid))

# ------------------------------------------------------------------------------------------------- clientes/proveedores
def siguiente_codigo_tercero(con, eid, tabla):
    mx = 0
    for (c,) in con.execute(f"SELECT codigo FROM {tabla} WHERE empresa_id=?", (eid,)):
        if c and c.strip().isdigit():
            mx = max(mx, int(c))
    return f"{mx + 1:05d}"

def guardar_tercero(con, eid, tabla, datos, tid=None):
    if tabla not in CAMPOS_TERCERO:
        raise ErrorNegocio("Tipo de ficha desconocido.")
    campos = CAMPOS_TERCERO[tabla]
    d = {k: (str(datos.get(k)).strip() if datos.get(k) not in (None, "") else None) for k in campos}
    if "recargo" in d:
        d["recargo"] = 1 if datos.get("recargo") in ("1", 1, True, "on") else 0
    if not d["nombre"]:
        raise ErrorNegocio("Falta el nombre.")
    if d["nif"]:
        d["nif"] = normalizar_nif(d["nif"])
    if d["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", d["email"]):
        raise ErrorNegocio(f"El correo electrónico «{d['email']}» no parece válido.")
    for k in ("descuento", "retencion"):
        if d.get(k):
            d[k] = d[k].replace(",", ".")
            try:
                float(d[k])
            except ValueError:
                raise ErrorNegocio(f"Número no válido: «{d[k]}».")
    d["codigo"] = d["codigo"] or siguiente_codigo_tercero(con, eid, tabla)
    otro = con.execute(f"SELECT id, nombre FROM {tabla} WHERE empresa_id=? AND codigo=?", (eid, d["codigo"])).fetchone()
    if otro and otro[0] != tid:
        raise ErrorNegocio(f"El código {d['codigo']} ya es de «{otro[1]}».")
    if tid:
        con.execute(f"UPDATE {tabla} SET {', '.join(k + '=?' for k in d)} WHERE id=? AND empresa_id=?", [*d.values(), tid, eid])
        return tid
    cols = list(d) + ["empresa_id"]
    return con.execute(f"INSERT INTO {tabla}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [*d.values(), eid]).lastrowid
