# Acceso desde el móvil

ContFactu puede dejar que un móvil Android emparejado consulte y haga facturas **mientras el programa
está abierto en el PC**. Los datos siguen en el PC. El móvil no se lleva una copia de la base ni una
copia de seguridad: pide cada factura, cada cliente o cada PDF cuando hace falta.

La opción viene **desactivada**. Si no la enciende, ContFactu se comporta como hasta ahora y solo se
abre en este equipo.

La aplicación Android se publica aparte. Este texto es para quien usa el programa en el PC.

## Encenderla

1. En ContFactu, abra **Ajustes**.
2. Marque **Permitir acceso desde el móvil** y pulse **Guardar**.
3. Pulse **Emparejar un dispositivo**. Aparecen un código QR, un código de respaldo (por si la cámara
   falla), las direcciones de este equipo, el puerto y la huella del certificado.
4. En el móvil, escanee el QR. La aplicación tiene que comprobar que la huella del certificado es la
   misma que se ve en el PC. Si no coincide, no debe continuar.
5. El móvil queda en la lista, con la fecha del último acceso. **Revocar** corta el acceso de ese
   aparato. Para volver a usarlo hay que emparejarlo otra vez.

El código caduca a los 10 minutos y solo vale una vez. Tras cinco códigos incorrectos el emparejamiento
se bloquea un cuarto de hora. Puede desbloquearlo en el mismo PC.

Para apagarlo, desmarque la casilla y guarde. El puerto se cierra. Los dispositivos emparejados se
conservan, pero no pueden conectar hasta que vuelva a activarlo.

## En la wifi de casa o de la oficina

El móvil y el PC tienen que estar en la **misma red**. Use la dirección que Ajustes marca como
«Wi-Fi o red local».

No abra puertos en el router. No active el reenvío de puertos ni el UPnP para esto. Quien no esté en
esa red no llega al PC, y quien esté necesita además haber emparejado el móvil.

Si Windows pregunta al abrir el puerto, permita ContFactu **solo en redes privadas**.

## Con datos móviles, por una VPN privada

Fuera de la wifi el móvil no debe entrar por Internet abierto. Use una VPN privada que ya tenga, en
los dos aparatos:

- **Tailscale**, o
- **WireGuard**.

Instálela en el PC y en el móvil, y únalos a la misma red privada (la misma tailnet o el mismo túnel).
No hace falta un nombre de dominio ni abrir el router: el móvil llama a la dirección que Ajustes marca
como Tailscale o WireGuard, igual que si estuviera en casa.

El código QR incluye las direcciones que el PC ve en ese momento. Si enciende la VPN después de generar
el código, genere otro para que salga la dirección nueva.

## Qué no sale del PC

La API no descarga la base de datos ni las copias de seguridad. El certificado y su clave privada
están en la carpeta de datos (`movil\`), no en la base y no en el `.zip` de las copias. La contraseña
del correo sigue en el Administrador de credenciales de Windows.

## Si algo no conecta

- ContFactu tiene que estar abierto.
- La opción tiene que seguir marcada.
- El móvil y el PC tienen que verse: misma wifi, o misma VPN.
- La huella del certificado tiene que ser la del QR. Si borró la carpeta `movil` de los datos, hay que
  emparejar de nuevo.
- Un dispositivo revocado tiene que emparejarse otra vez.
