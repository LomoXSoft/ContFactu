// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo.tls

import soft.lomox.contfactu.nucleo.HuellaMalFormada
import soft.lomox.contfactu.nucleo.QrInvalido
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Prueba y confirmación del emparejamiento a mano.
 * El orden de los bytes es el del PC: clave = código normalizado (8 letras, sin guion)
 * en UTF-8; mensaje = prefijo, un byte 0A y la huella canónica, también en UTF-8.
 */
object PruebaEmparejar {
    const val PREFIJO_PRUEBA = "contfactu-prueba-v1"
    const val PREFIJO_CONFIRMACION = "contfactu-confirmar-v1"

    fun prueba(codigo: String, huella: String): String = hmac(codigo, PREFIJO_PRUEBA, huella)

    fun confirmacion(codigo: String, huella: String): String = hmac(codigo, PREFIJO_CONFIRMACION, huella)

    /** Compara dos HMAC en hexadecimal. La comparación de los 32 bytes es en tiempo constante. */
    fun iguales(a: String?, b: String?): Boolean {
        val ba = hex(a) ?: return false
        val bb = hex(b) ?: return false
        return MessageDigest.isEqual(ba, bb)
    }

    private fun hmac(codigo: String, prefijo: String, huella: String): String {
        val clave = claveCodigo(codigo) ?: throw QrInvalido("El código de emparejamiento tiene que tener 8 caracteres.")
        val canon = Huellas.normalizar(huella) ?: throw HuellaMalFormada()
        val mensaje = (prefijo + "\n" + canon).toByteArray(Charsets.UTF_8)
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(clave.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return mac.doFinal(mensaje).joinToString("") { "%02x".format(it) }
    }

    private fun claveCodigo(codigo: String): String? {
        val limpio = codigo.uppercase().filter { it.isLetterOrDigit() }
        return limpio.takeIf { it.length == 8 }
    }

    private fun hex(valor: String?): ByteArray? {
        val x = valor?.trim()?.lowercase() ?: return null
        if (x.length != 64 || x.any { it !in "0123456789abcdef" }) return null
        return ByteArray(32) { i -> x.substring(i * 2, i * 2 + 2).toInt(16).toByte() }
    }
}
