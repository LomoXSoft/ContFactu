// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo.qr

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import soft.lomox.contfactu.nucleo.QrInvalido
import soft.lomox.contfactu.nucleo.tls.Huellas

/**
 * Lo que el PC enseña en el QR y en el código de respaldo.
 * El código queda en forma `XXXX-XXXX`. La huella, en `sha256:` y 64 hex minúsculas.
 */
data class CodigoQr(
    val hosts: List<String>,
    val puerto: Int,
    val codigo: String,
    val huella: String,
)

private val jsonQr = Json { ignoreUnknownKeys = true }

@Serializable
private data class QrBruto(
    val v: Int? = null,
    val app: String? = null,
    val hosts: List<String>? = null,
    val puerto: Int? = null,
    val codigo: String? = null,
    val huella: String? = null,
)

object AnalizadorQr {
    fun analizar(texto: String): CodigoQr {
        val raw = texto.trim().removePrefix("\uFEFF")
        if (raw.isEmpty()) throw QrInvalido("El código está vacío.")
        val obj = try {
            jsonQr.decodeFromString<QrBruto>(raw)
        } catch (_: Exception) {
            throw QrInvalido("El código no es un JSON de ContFactu.")
        }
        if (obj.v == null) throw QrInvalido("Falta la versión del QR.")
        if (obj.v != 1) throw QrInvalido("Este QR es de la versión ${obj.v}. Esta aplicación empareja la versión 1.")
        if (obj.app != "ContFactu") throw QrInvalido("Este QR no es de ContFactu.")
        val hosts = (obj.hosts ?: emptyList()).map { it.trim() }.filter { it.isNotEmpty() }.distinct()
        if (hosts.isEmpty()) throw QrInvalido("El QR no trae direcciones del PC.")
        val ajena = hosts.firstOrNull { !esIpv4(it) }
        if (ajena != null) throw QrInvalido("La dirección «$ajena» no es una IPv4.")
        val puerto = obj.puerto ?: throw QrInvalido("Falta el puerto.")
        if (puerto !in 1..65535) throw QrInvalido("El puerto no es válido.")
        val codigo = normalizarCodigo(obj.codigo) ?: throw QrInvalido("El código de emparejamiento tiene que tener 8 caracteres.")
        val huella = Huellas.normalizar(obj.huella) ?: throw QrInvalido("La huella del certificado no es un SHA-256 válido.")
        return CodigoQr(hosts, puerto, codigo, huella)
    }

    /**
     * Emparejamiento a mano: una dirección (IP o nombre) y el código.
     * La huella no se teclea; se comprueba luego con el PC.
     */
    fun manual(codigo: String, direccion: String, puertoTexto: String): DestinoManual {
        val host = direccion.trim()
        if (!esDestino(host)) throw QrInvalido("Escriba la dirección del PC: una IP o un nombre, sin más texto.")
        val puerto = puertoTexto.trim().ifEmpty { "8766" }.toIntOrNull()
        if (puerto == null || puerto !in 1..65535) throw QrInvalido("El puerto no es válido.")
        val normal = normalizarCodigo(codigo) ?: throw QrInvalido("El código de emparejamiento tiene que tener 8 caracteres.")
        return DestinoManual(host, puerto, normal)
    }
}

/** Lo que se escribe a mano. La huella llega después, cuando el PC la confirma. */
data class DestinoManual(
    val host: String,
    val puerto: Int,
    val codigo: String,
)

/** Ocho caracteres alfanuméricos, como `AB12-CD34`. El PC ignora espacios, guiones y mayúsculas. */
fun normalizarCodigo(codigo: String?): String? {
    val limpio = (codigo ?: "").uppercase().filter { it.isLetterOrDigit() }
    if (limpio.length != 8) return null
    return "${limpio.substring(0, 4)}-${limpio.substring(4)}"
}

/** IP o nombre de equipo. Una sola dirección, sin esquema ni ruta. */
fun esDestino(host: String): Boolean {
    val h = host.trim()
    if (h.isEmpty() || h.length > 253) return false
    if (esIpv4(h)) return true
    if (h.any { it.isWhitespace() || it in "/:@\\" }) return false
    return h.matches(
        Regex("""[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"""),
    )
}

fun esIpv4(host: String): Boolean {
    val partes = host.split('.')
    if (partes.size != 4) return false
    return partes.all { octeto ->
        if (octeto.isEmpty() || octeto.length > 3) return@all false
        val n = octeto.toIntOrNull() ?: return@all false
        n in 0..255
    }
}
