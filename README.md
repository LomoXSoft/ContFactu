# ContFactu

Programa de facturación para Windows 10/11 (también funciona en Linux y macOS) pensado para pequeñas empresas y autónomos.
Sirve como sustituto de **FactuCont 5**: puede **leer sus datos para importarlos** o empezar desde cero con una empresa nueva.

> ContFactu es un proyecto independiente. **No está afiliado a Binarema ni respaldado por ella.** «FactuCont» se nombra
> solo para indicar con qué formato de datos es compatible. Lee los archivos de FactuCont 5 (dBase y diseños `.fmt`)
> únicamente para que puedan pasarse a ContFactu. No incluye código, imágenes, iconos ni diseños de Binarema.

Interfaz en español, en su propia ventana (Edge WebView2) o en el navegador. Los datos se guardan solo en el ordenador,
en `%APPDATA%\ContFactu` (base de datos SQLite). No se envía nada a Internet.

Estado: **versión temprana (0.0.x)**. Use copias de seguridad.

![Primera pantalla](capturas/28_v003_bienvenida.png)

## Funciones

- **Primera pantalla** con dos opciones: empezar desde cero o importar de FactuCont.
- **Empresa nueva** con datos fiscales (con comprobación del NIF/CIF), serie y primer número de factura, tipos de IVA y logotipo.
  Se pueden tener **varias empresas**.
- **Importación de FactuCont 5** desde una carpeta `FC5`, un `.zip` o un `.rar`:
  - qué se importa: empresas, clientes, proveedores, facturas, albaranes, presupuestos, gastos, líneas y vencimientos;
  - conserva la numeración y se puede repetir;
  - verifica los totales línea a línea.
- **Facturas, presupuestos, albaranes y gastos**:
  - numeración correlativa `[serie][AA][número]` (p. ej. `260001`);
  - modificar y borrar, con aviso si se rompe la numeración;
  - **rectificativas** (serie R), por diferencias o por sustitución;
  - pasar presupuestos y albaranes a factura, juntando varios albaranes.
- **Cobros** totales o parciales, cobros pendientes y **recibos**.
- **Fichas de clientes y proveedores**.
- **PDF**:
  - con un diseño propio por defecto;
  - con el diseño `.fmt` de cada empresa importada, para que las facturas salgan como antes.
- **Libros de IVA** de emitidas y recibidas, con recargo de equivalencia y retenciones. Exportan a xlsx y CSV e incluyen un resumen **orientativo** del modelo 303.

Capturas (con datos inventados) en [`capturas/`](capturas/).

## Descargar

El instalador `ContFactu-Setup-<versión>.exe` está en [Releases](https://github.com/LomoXSoft/ContFactu/releases).
- Se instala en `C:\Program Files\ContFactu` y pide permiso de administrador.
- Los datos van en `%APPDATA%\ContFactu`, y desinstalar el programa no los borra.
- El instalador no está firmado digitalmente, así que Windows SmartScreen puede avisar.

## Ejecutar desde el código (desarrollo)

Requisitos: Python 3.12 o superior.

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m app                     # abre la ventana (o http://127.0.0.1:8765)
```

Variables de entorno útiles:

| Variable | Para qué sirve |
| --- | --- |
| `CONTFACTU_DATA` | Carpeta de datos. |
| `CONTFACTU_DB` | Ruta de la base de datos. |
| `CONTFACTU_PORT` | Puerto. |
| `CONTFACTU_NAVEGADOR=1` | Abre en el navegador en vez de la ventana propia. |
| `CONTFACTU_NO_BROWSER=1` | Arranca solo el servidor. |

Datos de demostración (empresa ficticia «Ferretería Ejemplo, S.L.»): `python -m herramientas.demo datos_demo/demo.db`
y después `CONTFACTU_DB=datos_demo/demo.db python -m app`.

## Pruebas

```bash
pip install -r requirements.txt
pytest -q
```

Las pruebas usan solo datos inventados. Algunas necesitan una copia real de FactuCont 5 y se saltan si no se indica:
`CONTFACTU_FC5=<carpeta FC5>` (empresas 00001 y 00008) y `CONTFACTU_RAR=<copia .rar>`. Nunca suba datos reales al repositorio.

## Construir el instalador (Windows)

Requisitos:
1. **Python 3.12** de 64 bits (python.org), en el PATH.
2. **Inno Setup 6** (jrsoftware.org).
3. Conexión a Internet la primera vez.

Después ejecute:

```bat
instalador\construir.bat
```

El script hace lo siguiente:
1. Crea `venv-win`, instala las dependencias y PyInstaller, y pasa las pruebas.
2. Descarga **7-Zip 25.01** de www.7-zip.org, comprueba su SHA-256 y lo deja en `instalador\7zip` (`instalador\obtener_7zip.ps1`). Sirve para abrir copias `.rar`. 7-Zip no está en el repositorio porque su licencia (LGPL con restricción unRAR) es distinta.
3. Empaqueta con PyInstaller (`instalador\ContFactu.spec`).
4. Comprueba que no se ha empaquetado ningún `.db`, `.dbf` ni `.pdf`.
5. Compila `instalador\ContFactu.iss`.

Resultado: `instalador\Output\ContFactu-Setup-<versión>.exe`. La versión se define solo en `app/__init__.py`.

## Estructura

| Ruta | Contenido |
| --- | --- |
| `app/main.py` | Web (FastAPI + Jinja2). |
| `app/db.py` | Esquema SQLite y migraciones. |
| `app/repo.py` | Consultas y numeración. |
| `app/calc.py` | Cálculos con `Decimal`. |
| `app/altas.py` | Empresas, clientes y proveedores nuevos, y validación del NIF. |
| `app/importer.py` | Lectura de los DBF de FactuCont 5. |
| `app/origen.py` | Carpeta, .zip o .rar de origen. |
| `app/fmt_pdf.py` | PDF por defecto e intérprete de los diseños `.fmt`. |
| `app/ventana.py` | Ventana con pywebview. |
| `app/iconos.py` | Iconos SVG propios. |
| `instalador/` | PyInstaller, Inno Setup y script de construcción. |
| `herramientas/` | Datos de demostración y pantalla de carga. |
| `tests/` | Pruebas (pytest). |

## Limitaciones

- Todavía no cumple **VERI\*FACTU** (RD 1007/2023): no hay registros encadenados, QR ni envío a la AEAT. El esquema ya tiene columnas `vf_*` preparadas.
- El resumen del modelo 303 es solo orientativo.
- Hasta 3 tipos de IVA por factura (como FactuCont).

## Licencia

ContFactu © 2026 **LomoXSoft**.

Este programa es software libre: puede redistribuirlo y/o modificarlo según los términos de la **Licencia Pública General
de GNU** publicada por la Free Software Foundation, ya sea la versión 3 de la Licencia o (a su elección) cualquier versión
posterior (GPL-3.0-or-later). Se distribuye con la esperanza de que sea útil, pero **SIN NINGUNA GARANTÍA**; ni siquiera
la garantía implícita de COMERCIABILIDAD o IDONEIDAD PARA UN PROPÓSITO PARTICULAR. Consulte el archivo [LICENSE](LICENSE).

Componentes de terceros que se usan al construir el instalador:
- Python, FastAPI, Uvicorn, Jinja2, ReportLab, dbfread, openpyxl, pywebview y Pillow, cada uno con su licencia.
- 7-Zip © Igor Pavlov (GNU LGPL + restricción unRAR), que se distribuye con su `License.txt`.
