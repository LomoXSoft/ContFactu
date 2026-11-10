# API del móvil (versión 1)

Contrato del PC para la aplicación Android de ContFactu 0.2.0. El servidor solo existe si el usuario
activó «Permitir acceso desde el móvil». Con la opción apagada no hay puerto a la escucha.

Base: `https://{host}:{puerto}/api/v1`

`host` y `puerto` salen del código QR. El PC puede anunciar varias direcciones (wifi, WireGuard,
Tailscale): se prueban en el orden del QR, con un tiempo corto cada una (2 o 3 segundos). La primera
que complete el TLS y presente la huella esperada es la buena.

Los importes y los tipos de IVA van en **texto**, con punto decimal (`"121.00"`, `"7.5"`). No se usan
números de coma flotante. En las peticiones también se admite la coma (`"7,5"`, `"100,00"`).

Las fechas son `AAAA-MM-DD`. Las respuestas de error son JSON: `{"error": "mensaje"}`. El emparejamiento
bloqueado añade `"reintentar_en"` (segundos).

No hay documentación interactiva en el servidor (`/docs` y `/openapi.json` no existen). Esta página es
el contrato.

## TLS

- TLS 1.2 como mínimo (en la práctica, 1.2 o 1.3).
- Certificado autofirmado de curva P-256, generado en el PC. El nombre del certificado no se comprueba.
- **Hay que anclar la huella.** No se usa el almacén de autoridades del sistema.
- La huella es SHA-256 del certificado en **DER** (el binario del certificado, no el texto PEM ni la
  clave pública suelta). En el QR va como `sha256:` seguido de 64 hexadecimales en minúsculas.
- Al conectar, se calcula esa huella y se compara con la del QR (da igual mayúsculas, dos puntos o el
  prefijo `sha256:`). Si no coincide, se cierra y no se envía el código ni el token.

## Código QR

Texto UTF-8 con un JSON. El orden de las claves no importa.

```json
{
  "v": 1,
  "app": "ContFactu",
  "hosts": ["192.168.1.20", "10.8.0.2", "100.64.1.5"],
  "puerto": 8766,
  "codigo": "AB12-CD34",
  "huella": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

| Campo | Significado |
| --- | --- |
| `v` | Versión de este QR. Si no es `1`, no se empareja. |
| `app` | Siempre `ContFactu`. |
| `hosts` | Direcciones IPv4. Primero la red local, luego WireGuard, luego Tailscale. |
| `puerto` | Puerto TCP. El de origen es el 8766; el PC puede usar otro. |
| `codigo` | Código de un solo uso, 8 caracteres `XXXX-XXXX`. Caduca a los 10 minutos. |
| `huella` | Huella que hay que anclar. |

El mismo código se enseña en el PC como **código de respaldo**, junto con las direcciones, el puerto y
la huella, por si la cámara no lee el QR. Al escribirlo a mano se ignoran espacios, guiones y
mayúsculas.

## Emparejar

`POST /api/v1/emparejar`

Sin token. Cuerpo:

```json
{"codigo": "AB12-CD34", "nombre": "Pixel de casa"}
```

`nombre` es el que verá el usuario en el PC (hasta 60 caracteres). Si falta, queda «Dispositivo móvil».

Respuesta `200`:

```json
{"token": "<secreto>", "dispositivo_id": 1, "nombre": "Pixel de casa"}
```

El `token` se entrega **una sola vez**. Hay que guardarlo en el almacén seguro del móvil (Android
Keystore). El PC solo conserva su hash SHA-256. Si se pierde el token, se revoca el dispositivo en el
PC y se empareja de nuevo.

| Código | Cuándo |
| --- | --- |
| 401 | Código incorrecto, caducado o ya usado. El texto no distingue el motivo. |
| 429 | Cinco fallos. `reintentar_en` indica los segundos que faltan (15 minutos desde el quinto fallo). Un acierto durante el bloqueo también responde 429 y no gasta el código. |
| 400 | Demasiados dispositivos (máximo 20) u otro rechazo explicado en `error`. |

Mientras la opción está apagada, cualquier ruta de esta API responde `404` con `{"error": "No disponible."}`.

## Autenticación del resto

```
Authorization: Bearer <token>
```

Solo esa cabecera. Un token en la query se ignora. Sin token, con un token desconocido o con uno
revocado: `401` y `{"error": "Acceso no autorizado."}`. No se distingue el caso. Revocar en el PC
tiene efecto en la siguiente petición.

Cada petición aceptada actualiza la fecha de último acceso que se ve en Ajustes.

## Rutas

El token da acceso a todas las empresas del PC. No hay borrado, ni correo, ni copias, ni descarga de
`contfactu.db`.

### `GET /api/v1/salud`

Sin datos de negocio. Sirve para comprobar que se llegó al PC después de anclar la huella.

```json
{"nombre": "ContFactu", "api": 1, "version": "0.2.0"}
```

`api` es la versión de este contrato. `version` es la de ContFactu.

### `GET /api/v1/empresas`

```json
{"empresas": [{"id": 1, "codigo": "00001", "nombre": "Ejemplo SL", "nif": "B00000000",
  "ivas": ["21", "10", "4", "0"], "re_tasas": {"21": "5.2", "10": "1.4"}, "n_facturas": 3}]}
```

`ivas` son los tipos habituales de la empresa, el primero es el de por defecto. **No son una lista
cerrada**: cada línea de factura acepta cualquier tipo entre 0 y 100 con hasta dos decimales
(por ejemplo `7.5`). `re_tasas` es el recargo de equivalencia que el PC aplicará si en la factura se
envía `"re": true`.

### `GET /api/v1/empresas/{id}/facturas`

Query: `anio` (si se omite, el año más reciente; `todos` para todos), `q` (nombre, NIF o número) y
`limite` (de 1 a 500, por defecto 200).

```json
{"anio": "2026", "anios": ["2026", "2025"], "facturas": [
  {"id": 10, "numero": "260001", "serie": "", "numero_visible": "260001", "fecha": "2026-11-10",
   "nombre_f": "Cliente Uno SL", "nif": "12345678Z", "total": "228.50", "pendiente": "228.50",
   "estado": "pendiente"}]}
```

`estado` es `pendiente`, `parcial` o `cobrado`. Solo facturas emitidas (no albaranes, presupuestos ni gastos).

### `GET /api/v1/empresas/{id}/facturas/{factura}`

La factura con sus líneas y el desglose. `404` si no es una factura de esa empresa.

```json
{"id": 10, "numero": "260001", "serie": "", "numero_visible": "260001", "fecha": "2026-11-10",
 "fecha_operacion": "2026-11-10", "nombre_f": "Cliente Uno SL", "direccion_f": "C/ Falsa 1",
 "ciudad_f": "Madrid", "nif": "12345678Z", "cliente_codigo": "C1", "forma_pago": null,
 "descuento": "0", "retencion": "0", "exento": false, "iva_incluido": false, "re": false,
 "total": "228.50", "pendiente": "228.50", "estado": "pendiente",
 "desglose": [{"base": "100.00", "iva": "21", "re": "0"}, {"base": "100.00", "iva": "7.5", "re": "0"}],
 "lineas": [{"orden": 1, "codigo": "", "concepto": "Tornillos", "cantidad": "1", "precio": "100",
             "descuento": "0", "iva": "21", "comentario": false}]}
```

El número lo asigna el PC. No se envía en el alta y no se puede cambiar al editar.

### `POST /api/v1/empresas/{id}/facturas`

Crea una factura. Respuesta `201` con el mismo objeto que el GET de detalle.

```json
{"fecha": "2026-11-10", "serie": "", "cliente_id": 3, "nombre_f": "Cliente Uno SL",
 "direccion_f": "C/ Falsa 1", "ciudad_f": "Madrid", "nif": "12345678Z", "cliente_codigo": "C1",
 "forma_pago": "", "domiciliacion": "", "ccc": "", "descuento": "0", "retencion": "0",
 "re": false, "exento": false, "iva_incluido": false,
 "lineas": [
   {"concepto": "Tornillos", "cantidad": "2", "precio": "10.50", "descuento": "0", "iva": "21"},
   {"concepto": "Especial", "cantidad": "1", "precio": "100", "iva": "7,5"},
   {"concepto": "Nota interna", "comentario": true}
 ]}
```

- `cliente_id` es opcional. Si se envía, el PC rellena los datos de cabecera que vengan vacíos
  (nombre, NIF, dirección, código, forma de pago y, si no se manda descuento, el de la ficha).
- `nombre_f` es obligatorio al final (propio o sacado del cliente).
- `serie` son como mucho 3 caracteres. Si no se envía, la factura va sin serie.
- En cada línea, `iva` vacío significa 21. `comentario: true` es una línea sin importe.
- `re: true` aplica el recargo de equivalencia de la empresa. Por defecto es false.
- Los totales, la numeración y el orden de fechas de la serie los calcula el PC con las mismas reglas
  que la ventana. Un tipo de IVA ilegal (por ejemplo 150, o más de dos decimales) responde `400` con
  el mensaje del programa y no crea la factura.

### `PUT /api/v1/empresas/{id}/facturas/{factura}`

El mismo cuerpo que el alta. Sustituye las líneas y recalcula. No cambia el número ni la serie.
Si ya hay cobros que no caben en el nuevo total, responde `400` y no modifica nada. Respuesta `200`
con la factura ya guardada.

### `GET /api/v1/empresas/{id}/facturas/{factura}/pdf`

El PDF, `Content-Type: application/pdf`. Es el mismo documento que genera la ventana (diseño de la
empresa o el diseño por defecto).

### `GET /api/v1/empresas/{id}/clientes`

Query: `q` y `limite` (igual que en facturas).

```json
{"clientes": [{"id": 3, "codigo": "C1", "nombre": "Cliente Uno", "nombre_f": "Cliente Uno SL",
  "nif": "12345678Z", "direccion": null, "direccion_f": null, "ciudad": "Madrid", "ciudad_f": null,
  "telefono": null, "movil": null, "email": "cliente@example.com", "contacto": null,
  "forma_pago": null, "dias_pago": null, "descuento": null, "recargo": null, "retiene": null,
  "ccc": null, "bic": null, "domiciliacion": null}]}
```

### `GET /api/v1/empresas/{id}/clientes/{cliente}`

El mismo objeto de un cliente. `404` si no es de esa empresa.

### `GET /api/v1/empresas/{id}/buscar?q=`

La misma búsqueda del PC, limitada a **clientes y facturas** (como mucho 25 de cada). Menos de dos
caracteres no busca, salvo que la consulta sea un número.

```json
{"q": "Cliente", "clientes": [{"id": 3, "codigo": "C1", "nombre": "Cliente Uno",
  "nombre_f": "Cliente Uno SL", "nif": "12345678Z", "ciudad": "Madrid"}],
 "facturas": [{"id": 10, "numero_visible": "260001", "fecha": "2026-11-10",
  "nombre_f": "Cliente Uno SL", "nif": "12345678Z", "total": "228.50",
  "pendiente": "228.50", "estado": "pendiente"}],
 "total": 2}
```

## Qué no está

No hay rutas para copias de seguridad, para bajar `contfactu.db`, para borrar facturas, para el correo,
para proveedores ni para presupuestos, albaranes o gastos. Un `GET` a esas rutas responde `404`.
