// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo

/**
 * Fallo del contrato con el PC. El texto es la causa técnica; la interfaz
 * lo cuenta en español, sin mezclarlo con datos de negocio.
 */
sealed class ErrorContFactu(mensaje: String) : Exception(mensaje)

class QrInvalido(mensaje: String) : ErrorContFactu(mensaje)

class HuellaMalFormada(
    mensaje: String = "La huella no tiene 64 hexadecimales SHA-256.",
) : ErrorContFactu(mensaje)

/** El certificado presentado no es el del QR. No se ha enviado código ni token. */
class HuellaRechazada(
    mensaje: String = "La huella del certificado no coincide.",
) : ErrorContFactu(mensaje)

class SinTls(mensaje: String = "La conexión no usa TLS.") : ErrorContFactu(mensaje)

class PcInalcanzable(mensaje: String) : ErrorContFactu(mensaje)

/** El puerto contestó, pero la opción del móvil está apagada. */
class AccesoApagado(mensaje: String) : ErrorContFactu(mensaje)

/** Token ausente, desconocido o revocado. La API no distingue el caso. */
class AccesoRevocado(mensaje: String) : ErrorContFactu(mensaje)

class CodigoInvalido(
    mensaje: String = "El código es incorrecto, ha caducado o ya se ha usado.",
) : ErrorContFactu(mensaje)

/** El PC no confirmó la huella vista. No se ancla y no se envía el código. */
class ConfirmacionInvalida(
    mensaje: String = "La confirmación del PC no coincide con el certificado visto. No se ha anclado la huella ni se ha enviado el código.",
) : ErrorContFactu(mensaje)

class EmparejamientoBloqueado(val reintentarEn: Int, mensaje: String) : ErrorContFactu(mensaje)

class NoEncontrado(mensaje: String) : ErrorContFactu(mensaje)

class PeticionRechazada(
    val estado: Int,
    mensaje: String,
    val campo: String? = null,
    val indice: Int? = null,
) : ErrorContFactu(mensaje)

class RespuestaInesperada(mensaje: String) : ErrorContFactu(mensaje)

class SinSesion(mensaje: String = "Este móvil no está emparejado.") : ErrorContFactu(mensaje)

/**
 * La lanza el TrustManager. Tiene que ser una [java.security.cert.CertificateException]
 * para que TLS cierre el apretón de manos antes de cualquier petición HTTP.
 */
class CertificadoNoAnclado(mensaje: String) : java.security.cert.CertificateException(mensaje)
