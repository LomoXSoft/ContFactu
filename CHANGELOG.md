# Cambios en ContFactu

Formato: cada versión con lo nuevo, lo cambiado y lo corregido. La versión sale de un único sitio:
`app/__init__.py` (`__version__`). Autor: **LomoXSoft**.

La 0.0.3 es la primera versión publicada en GitHub. La 0.0.1 y la 0.0.2 fueron versiones de prueba sin publicar; su
historial de git no forma parte de este repositorio.

## [0.2.0] — 2026-11-10

Acceso opcional desde un móvil emparejado. Viene **desactivado**: quien actualiza desde la 0.1.0 sigue
igual (la ventana escucha solo en este equipo) hasta que lo active en Ajustes. Los datos no se mueven de
sitio y, antes de poner al día la base, se hace la copia de siempre.

La aplicación Android no entra en esta versión. Aquí está el lado PC y el contrato que esa aplicación
consumirá (`docs/api-movil.md`).

### Nuevo
- **Ajustes → «Permitir acceso desde el móvil»**, desactivado de origen. Sin avisos al abrir.
- Al activarlo: emparejamiento con código QR y código de respaldo, lista de dispositivos con el último
  acceso y botón para revocar cada uno.
- Servidor aparte, solo con la API del móvil, cifrado con un certificado autofirmado. La huella SHA-256
  va en el QR para que el móvil la ancle. El token de cada dispositivo se guarda solo como hash.
- El emparejamiento se bloquea tras 5 códigos incorrectos.
- Escucha en la wifi y en una VPN privada (WireGuard o Tailscale) sin abrir puertos del router.
  Guía: `docs/acceso-movil.md`.
- API 1: empresas, facturas (consultar, crear, editar y PDF), clientes y búsqueda. El IVA de cada línea
  sigue siendo libre. No hay descarga de la base ni de las copias.

### Cambiado
- Esquema 5 (tabla `dispositivos_movil`). Una base de la 0.1.0 se copia antes de crearla y conserva
  empresas, facturas y clientes. La opción queda desactivada.

### Corregido
- Al crear o modificar una empresa, un dato rechazado (por ejemplo un NIF no válido) volvía a pintar el
  formulario y, si un tipo de IVA o un recargo llevaba coma, espacios o un texto, la ventana se quedaba en
  «Internal Server Error». El aviso sale ahora en el propio campo (NIF, código postal, IVA, recargo, descuento…)
  y se conserva lo escrito. El fallo del re-render ya estaba en la 0.1.0.
- Un tipo de IVA, un recargo de equivalencia o un descuento en porcentaje solo se acepta entre 0 % y 100 %,
  ambos incluidos, con los decimales que se escriban. Vale en el formulario, en la ficha del cliente y en la API del móvil.

### Dependencias
- `cryptography`, para crear el certificado del acceso móvil. No se usa mientras la opción está desactivada.

### Comprobación
- Pruebas automáticas con datos sintéticos: opción apagada, escucha solo local, rechazo sin token o con
  token revocado, límite de intentos y TLS con la huella anclada.
- En la preparación de esta versión **no se ha abierto la ventana real de Windows** ni se ha probado con
  un móvil Android. El TLS se ha probado en local, de extremo a extremo, con un cliente de pruebas.

## [0.1.0] — 2026-11-07

Corrige el bloqueo al abrir la ventana propia en Windows. No añade pantallas, avisos ni opciones.
Es una versión normal (no una pre-release): el número no lleva sufijo de candidata. Los datos siguen en
`%APPDATA%\ContFactu` y no se migran a otro sitio.

La 0.0.1 no lo sufría: se abría en el navegador. A partir de la ventana propia, pywebview 5 y posteriores
recorren los atributos públicos del puente con la página. La construcción instala `pywebview>=5`; al
preparar esta versión eso es la 6.2.1, que es la que reproduce el error. El puente guardaba la ventana
en un atributo público.

### Corregido
- **La ventana dejaba de responder al arrancar** (visto en la 0.0.5 al actualizar desde la 0.0.1).
  La pantalla principal llegaba a pintarse, el programa no respondía, la pantalla de carga seguía delante
  y había que forzar el cierre. Windows lo registraba como Application Hang 1002 / AppHangB1, con WebView2
  y pythonnet en el proceso.
- El registro de pywebview era `Error while processing ventana.native.AccessibilityObject.Bounds.Empty…`
  (`maximum recursion depth exceeded`) y también `Empty.Location`. El recorrido entra en el control nativo
  de WebView2 y en Windows bloquea el arranque. Ocurre antes del aviso de «página cargada», que es el que
  cierra la pantalla de carga; por eso el splash no desaparecía.
- La ventana queda en un atributo privado, que pywebview no recorre. Abrir un PDF, guardar un Excel o CSV
  y elegir carpeta o copia usan esa misma ventana. El servidor se detiene al cerrarla, como hasta ahora.

### Comprobación
- Pruebas automáticas con datos sintéticos: el recorrido real de la pywebview instalada ya no entra en el
  control nativo; la pantalla de carga se cierra al cargar; los diálogos y el cierre del servidor siguen
  en su sitio.
- En la preparación de esta versión **no se ha abierto la ventana real de Windows** ni se ha generado aquí
  el instalador. Hay que construir `ContFactu-Setup-0.1.0.exe` en un equipo de compilación y probar el
  arranque antes de publicar la release.

## [0.0.5] — 2026-11-02

Regla de esta versión: **todo lo nuevo es opcional y viene desactivado**. Quien actualiza desde la 0.0.4 sigue igual
(mismos avisos, nada nuevo al abrir ni al cerrar) hasta que lo activa. Hay pruebas que comprueban estos valores por defecto.

### Nuevo
- **Copias automáticas** (menú «Copias» → «Copias automáticas»), **desactivadas por defecto**:
  - al cerrar ContFactu (por defecto), una vez al día al abrirlo, o ambas; sin preguntas ni ventanas;
  - en la carpeta que se elija (pendrive, Google Drive, OneDrive…); por defecto, la de las copias manuales;
  - se guardan las últimas 10 (de 1 a 200); solo se borran las automáticas antiguas (`ContFactu-auto-….zip`);
  - si la carpeta no está disponible, la copia va a `%APPDATA%\ContFactu\copias-automaticas` y se avisa al abrir.
- **Restaurar desde la lista «Copias disponibles»**: copias manuales, automáticas y de seguridad de las tres carpetas,
  con su tipo, fecha y tamaño. La vista previa indica si la copia es de una versión anterior (se pone al día al restaurar).
- **Buscador global**: casilla «Buscar…» en la barra superior de cada empresa (o `Ctrl+K`). Encuentra clientes y
  proveedores (nombre, NIF), documentos de cualquier tipo (número, nombre, NIF, importe, concepto) y productos. Se recorre
  con el teclado (↓ ↑ e Intro). Nunca se abre ni se enfoca sola.
- **«No volver a recordar»** en el aviso de 7 días sin copia. Se vuelve a activar en «Copias» → «Recordatorio».
- **Enlace a Ko-fi** en «Acerca de» (una línea pequeña; se abre en el navegador del sistema). Sin ventanas ni avisos.

### Cambiado
- `construir.bat` puede construir **sin Internet**: reutiliza una copia de 7-Zip 25.01 ya comprobada por SHA-256
  (`%LOCALAPPDATA%\ContFactu-build\7zip-25.01`, `C:\Program Files\7-Zip` o `CONTFACTU_7ZIP_DIR`) antes de descargarlo.
- Las pruebas de versiones anteriores ya no tienen la versión escrita a mano.

## [0.0.4] — 2026-11-02

### Nuevo
- **Copias de seguridad en un clic** (menú «Copias»):
  - un `.zip` con fecha y hora con la base de datos (copiada con la función de copia de SQLite, coherente aunque el
    programa esté abierto), los logotipos y los ajustes;
  - en la carpeta que elija el usuario, que se recuerda; por defecto `Documentos\ContFactu-Copias`;
  - **restaurar** con vista previa del contenido y confirmación, y copia automática previa de los datos actuales;
  - recordatorio al abrir si pasan más de 7 días sin copia (configurable; 0 = sin aviso).
- **Actualización segura**: la base de datos guarda la versión del programa y del esquema. La primera vez que se abre
  una versión nueva se hace una copia automática (`copias-automaticas\ContFactu-antes-de-<versión>-….zip`) **antes** de
  poner al día la base. Pruebas que simulan bases de la 0.0.1 y la 0.0.3. El README explica cómo comprobarlo.
- **Enviar facturas por correo** con el PDF adjunto:
  - servidor SMTP por empresa (SSL o STARTTLS) y botón «Probar conexión»;
  - la contraseña se guarda en el Administrador de credenciales de Windows, nunca en la base de datos;
  - asunto y texto editables con marcadores (`{numero}`, `{fecha}`, `{total}`, `{cliente}`…);
  - el correo del cliente sale de su ficha; siempre hay vista previa y solo se envía al pulsar «Enviar»;
  - cada envío (o error) queda anotado en el documento.
- **Exportar a Excel**:
  - libros de IVA con columnas al estilo de los libros registro de la AEAT (ejercicio, periodo, fechas, serie y número,
    NIF, base, tipo, cuota, recargo, retención, total…), resumen por tipo y resumen orientativo del 303;
  - listados de facturas (y demás documentos), clientes, proveedores y cobros pendientes;
  - fechas y euros con formato, fila de totales, cabecera fija y filtros.
- **Avisos de cobro al abrir**: cobros vencidos y que vencen en los próximos 7 días, con enlace a cobros pendientes.
  Se pueden ocultar hasta que se vuelva a abrir el programa.

### Cambiado
- **IVA sin límites**: en cada línea vale cualquier tipo entre 0 y 100 % con hasta 2 decimales (p. ej. 7,5 %), y una
  factura puede tener tantos tipos distintos como haga falta (antes, como en FactuCont, un máximo de 3).
  - Cada empresa tiene una tabla editable de tipos habituales con su recargo de equivalencia (antes los recargos eran fijos).
  - Totales, libros, resumen del 303, PDF por defecto y diseños `.fmt` tienen en cuenta todos los tipos. En los diseños
    `.fmt`, si hay más de 3, se imprimen todos con letra más pequeña.
  - Las facturas antiguas e importadas no cambian.
- El PDF del documento se comparte entre la descarga y el envío por correo.

### Dependencias
- `keyring` (para guardar la contraseña del correo en el Administrador de credenciales de Windows).

## [0.0.3] — 2026-11-02

### Nuevo
- **Primera pantalla con dos opciones**: «Empezar desde cero» o «Importar de FactuCont». Ya no hace falta importar nada para empezar.
- **Empresa nueva desde cero**, con un formulario que pide:
  - razón social, NIF/CIF (se comprueba la letra o el dígito de control), dirección, código postal, población, provincia,
    teléfono, correo y código de empresa (00001…);
  - serie y primer número de factura: la numeración es serie + año + correlativo, y el primer número sirve para continuar
    la de otro programa;
  - tipos de IVA habituales y logotipo opcional.
- **Diseño de factura por defecto** para las empresas sin diseños de FactuCont. Lleva el logotipo, los datos fiscales de
  emisor y cliente, el desglose de IVA (y de recargo de equivalencia, si lo hay), la retención, los vencimientos y la
  cuenta para transferencias. Sirve también para presupuestos, albaranes y gastos.
- **Fichas de clientes y proveedores**: alta y modificación, con código automático. Nueva lista de proveedores. Desde la
  ficha de un cliente se puede facturarle directamente.
- **Datos de la empresa** editables en el menú «Empresa».
- **Varias empresas**. Desde «Cambiar de empresa» se puede:
  - crear otra empresa nueva;
  - importar de FactuCont en cualquier momento.

  Una importación nunca se mezcla con una empresa creada en ContFactu que tenga el mismo código: avisa y la omite.

### Cambiado
- Capturas de demostración renovadas, con un logotipo inventado completo y una ruta de datos típica de Windows. Nueva prueba que confirma que el logotipo se encaja en la factura sin recortarse ni deformarse.
- La primera pantalla dice «Bienvenido a ContFactu». Los textos que se dirigen al usuario usan el masculino genérico.
- **Código publicado como software libre** bajo la licencia GPL-3.0-or-later (archivo LICENSE; aviso en «Acerca de»).
  7-Zip ya no está en el repositorio: `construir.bat` lo descarga de 7-zip.org y comprueba su SHA-256.
- **Instalación en Archivos de programa** (`C:\Program Files\ContFactu`, 64 bits), para todo el equipo. El instalador
  pide permiso de administrador.
  - Al actualizar desde la 0.0.1 o la 0.0.2 (que se instalaban por usuario en `%LOCALAPPDATA%\Programs\ContFactu`),
    se desinstala sola esa copia antigua: programa, accesos directos y entrada en «Aplicaciones». Así no quedan
    entradas duplicadas.
  - Los **datos siguen en `%APPDATA%\ContFactu`** y no se tocan.
  - Si ContFactu está abierto, el instalador pide cerrarlo.
- El perfil de la ventana (WebView2), los logotipos, la base de datos y el registro van siempre en `%APPDATA%\ContFactu`.
  ContFactu nunca escribe en su carpeta de instalación.
- Al terminar la instalación, «Abrir ContFactu» lo abre con la cuenta del usuario, no como administrador.

## [0.0.2] — 2026-10-31

### Nuevo
- **Programa independiente**: ContFactu se abre en su propia ventana (Edge WebView2, a través de pywebview),
  con título «ContFactu 0.0.2», icono propio, tamaño 1280×860 redimensionable y maximizable.
  - Al cerrar la ventana se detiene el servidor interno.
  - Una sola instancia: si se vuelve a abrir, se trae al frente la ventana que ya estaba abierta.
  - PDF (facturas, recibos): se abren en el visor de PDF predeterminado de Windows para verlos o imprimirlos.
  - Excel/CSV (libros de IVA, listados): diálogo nativo «Guardar como».
  - Si el equipo no tiene WebView2, ContFactu se abre en el navegador como en la 0.0.1.
- **Pantalla de carga (splash)** propia: cuadrada, sin bordes y centrada, con «ContFactu», la versión y «LomoXSoft».
  Aparece en cuanto se lanza el programa y se cierra cuando la ventana principal está lista.
  Su estilo se inspira en el de FactuCont, sin reutilizar su imagen.
- **Iconos junto al texto** en el menú y en los botones principales.
  - Son dibujos propios en SVG que mantienen los colores y las formas que se asociaban a cada función en FactuCont:
    - facturas en verde, albaranes en azul, presupuestos en amarillo y gastos en granate;
    - clientes en verde y proveedores en granate;
    - impresora, ojo, papelera, lápiz, lupa, libro, etc.
  - No se copia ningún mapa de bits de Binarema.
- Página **Acerca de**: versión, autor (LomoXSoft), carpeta de datos, modo de pantalla (ventana o navegador),
  pantalla de carga, galería de iconos y créditos (7-Zip).
- **Versión visible** en:
  - el título de la ventana y el pie de página;
  - Acerca de;
  - las propiedades del .exe (Detalles);
  - el instalador `ContFactu-Setup-0.0.2.exe`.

### Cambiado
- El instalador **actualiza encima** de la 0.0.1:
  - mismo identificador de aplicación y misma carpeta;
  - cierra ContFactu si está abierto;
  - sustituye las bibliotecas antiguas;
  - **conserva los datos** de `%APPDATA%\ContFactu`.

## [0.0.1] — primera versión instalada

- Facturas, albaranes, presupuestos y gastos.
  - Numeración por serie y año.
  - Crear, modificar y borrar, con avisos si se borra un documento que no es el último.
- Facturas **rectificativas**, por diferencias o por sustitución, con referencia a la original.
- **Cobros y recibos**:
  - cobros parciales o totales y anulación;
  - cobros pendientes;
  - recibos en PDF con el diseño de FactuCont.
- **Convertir** presupuesto o albarán(es) en factura.
- **Libros de IVA** (emitidas y recibidas) y resumen para el **modelo 303**, en pantalla, Excel y CSV.
- PDF de facturas con el diseño de FactuCont.
- **Asistente de importación** desde FactuCont 5:
  - el origen lo elige el usuario (carpeta, .zip o .rar), sin ruta por defecto;
  - busca la carpeta FC5 dentro de subcarpetas;
  - abre los .rar con un 7-Zip incluido, sin necesidad de WinRAR.
- **Instalador para Windows** (Inno Setup). No incluye datos: estos se guardan en `%APPDATA%\ContFactu`.
