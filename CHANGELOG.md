# Cambios en ContFactu

Formato: cada versión con lo nuevo, lo cambiado y lo corregido. La versión sale de un único sitio:
`app/__init__.py` (`__version__`). Autor: **LomoXSoft**.

La 0.0.3 es la primera versión publicada en GitHub. La 0.0.1 y la 0.0.2 fueron versiones de prueba sin publicar; su
historial de git no forma parte de este repositorio.

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
