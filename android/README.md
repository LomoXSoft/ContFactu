# ContFactu para Android 0.2.0 (beta)

Cliente libre del programa de escritorio [ContFactu](../README.md). **De momento es una beta.**
Lleva la misma numeración que el programa del PC: esta 0.2.0 va con ContFactu 0.2.0.

Los datos de negocio viven en el PC. Esta aplicación no guarda facturas, clientes ni copias:
consulta y edita a través de la API del móvil (`/api/v1`; contrato en [`../docs/api-movil.md`](../docs/api-movil.md)
y guía en [`../docs/acceso-movil.md`](../docs/acceso-movil.md)).

Marca: **LomoXSoft**. Licencia: **GPL-3.0-or-later**, como el resto del repositorio (véase [`../LICENSE`](../LICENSE)).
Los cambios están en el [`CHANGELOG.md`](../CHANGELOG.md) general.

## Qué hace

- Empareja con el QR del PC (la huella va en el QR) o a mano, con la dirección y el código. A mano el puerto es 8766 salvo que se cambie, y la huella se confirma con el PC antes de anclarla.
- Prueba las direcciones del QR en orden.
- Ancla la huella SHA-256 del certificado en DER y rechaza cualquier otra, y también el tráfico sin TLS.
- Lista, ve, crea y edita facturas (el IVA de cada línea es libre). El número y el total los calcula el PC.
- Lista clientes, busca clientes y facturas, y muestra el PDF.
- Guarda el token y la huella cifrados con el Android Keystore. «Olvidar este PC» los borra.
- El PDF queda en la caché temporal y se borra al salir de la pantalla y al cerrar la aplicación.

## Requisitos

- JDK 17 o superior.
- Android SDK, `compileSdk` 35. `ANDROID_HOME` o `local.properties` (`sdk.dir`).
- minSdk 26. Sin servicios de Google, sin analítica y sin publicidad.

## Compilar

```bash
./gradlew :nucleo:test
./gradlew :app:assembleDebug
./gradlew :app:assembleRelease
```

Las pruebas de `:nucleo` no necesitan emulador: parseo del QR, anclaje de la huella
(acepta la correcta, rechaza otra y rechaza una conexión sin TLS) y el cliente de la API
contra un servidor simulado.

La integración con un ContFactu real es opcional. Si existe el archivo que indica
`CONTFACTU_IT` (por defecto `/tmp/contfactu-it.json`) con
`{"hosts":["127.0.0.1"],"puerto":8766,"codigo":"AB12-CD34","huella":"sha256:…"}`,
`IntegracionPcTest` empareja, crea una factura sintética y pide el PDF.
Sin ese archivo la prueba se omite.

## Firma

Las APK que se publican en GitHub se firman con la **clave de publicación de LomoXSoft**
(certificado `CN=ContFactu, O=LomoXSoft, C=ES`). Su huella SHA-256 figura en las notas de cada versión.
La clave y su contraseña **no están en el repositorio** ni se publican: se guardan aparte, y solo
quien mantiene la app puede firmar con ella. Así, cada versión nueva se instala encima de la anterior
y nadie más puede publicar una APK que pase por ella.

`assembleRelease` busca la configuración de firma en un archivo de propiedades **fuera de git**:

1. el que indique la variable de entorno `CONTFACTU_FIRMA`, o
2. `android/keystore.properties`, que `.gitignore` excluye.

Formato (hay un ejemplo sin secretos en `keystore.properties.example`): `storeFile`, `storePasswordFile`
(un archivo con la contraseña, con permisos 600) o `storePassword`, `keyAlias` y, opcional, `keyPassword`.
Las rutas relativas se resuelven desde la carpeta del archivo de propiedades.

```bash
CONTFACTU_FIRMA=/ruta/privada/firma.properties ./gradlew :app:assembleRelease
apksigner verify --print-certs app/build/outputs/apk/release/ContFactu-0.2.0-release.apk
```

Sin ese archivo, `assembleRelease` genera una APK sin firmar (`…-release-unsigned.apk`), que cada cual
puede firmar con su propia clave para probarla. Una APK firmada con otra clave no se instala encima de la
publicada: hay que desinstalar antes la otra.

No incluya nunca `*.jks`, `*.keystore`, `*.p12`, contraseñas ni `keystore.properties` en un commit.

## Permisos

Internet, para hablar con el PC, y la cámara, solo para leer el QR. El código de respaldo
no necesita cámara.
