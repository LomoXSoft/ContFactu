// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo.tls

import okhttp3.ConnectionSpec
import okhttp3.OkHttpClient
import soft.lomox.contfactu.nucleo.CertificadoNoAnclado
import soft.lomox.contfactu.nucleo.HuellaMalFormada
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * Huella SHA-256 del certificado en DER, la misma que ContFactu pone en el QR:
 * `sha256:` y 64 hexadecimales. No es la huella de la clave pública.
 */
object Huellas {
    fun de(certificado: X509Certificate): String = de(certificado.encoded)

    fun de(der: ByteArray): String {
        val dig = MessageDigest.getInstance("SHA-256").digest(der)
        return "sha256:" + dig.joinToString("") { "%02x".format(it) }
    }

    /**
     * Acepta mayúsculas, espacios, dos puntos entre bytes y el prefijo `sha256:` o `sha256/`.
     * Devuelve la forma canónica, o null si no son 64 hexadecimales.
     */
    fun normalizar(valor: String?): String? {
        var x = valor?.trim()?.lowercase()?.replace(" ", "") ?: return null
        if (x.startsWith("sha256:")) x = x.substring(7)
        else if (x.startsWith("sha256/")) x = x.substring(7)
        x = x.replace(":", "")
        if (x.length != 64 || x.any { it !in "0123456789abcdef" }) return null
        return "sha256:$x"
    }

    fun iguales(a: String?, b: String?): Boolean {
        val na = normalizar(a) ?: return false
        val nb = normalizar(b) ?: return false
        return MessageDigest.isEqual(na.toByteArray(Charsets.US_ASCII), nb.toByteArray(Charsets.US_ASCII))
    }
}

/**
 * No usa el almacén del sistema. Solo pasa el certificado hoja cuya huella DER
 * coincide con la del QR. El nombre del certificado no se mira: el PC lo firma
 * como «ContFactu» y la dirección es una IP.
 *
 * OkHttp trae un [okhttp3.CertificatePinner] que ancla la clave pública (SPKI),
 * no el certificado entero. Por eso el anclaje está aquí.
 */
class AnclajeHuella(huellaEsperada: String) : X509TrustManager {
    private val esperada: String = Huellas.normalizar(huellaEsperada)
        ?: throw HuellaMalFormada()

    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
        throw CertificateException("Este cliente no presenta certificado de cliente.")
    }

    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
        val hoja = chain?.firstOrNull()
            ?: throw CertificadoNoAnclado("El servidor no ha presentado certificado.")
        val calculada = Huellas.de(hoja)
        if (!Huellas.iguales(calculada, esperada)) {
            throw CertificadoNoAnclado("La huella del certificado no coincide.")
        }
    }

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
}

object TlsAnclado {
    /**
     * Cliente que solo habla TLS 1.2 o superior y solo con la huella indicada.
     * El verificador de nombre acepta la IP porque la comprobación real es la huella;
     * sin huella coincidente el TrustManager ya ha cerrado el apretón de manos.
     */
    fun cliente(huella: String, conectaMs: Long = 3_000, llamaMs: Long = 8_000): OkHttpClient {
        val anclaje = AnclajeHuella(huella)
        val contexto = SSLContext.getInstance("TLS")
        contexto.init(null, arrayOf<TrustManager>(anclaje), SecureRandom())
        return OkHttpClient.Builder()
            .sslSocketFactory(contexto.socketFactory, anclaje)
            .hostnameVerifier { _, _ -> true }
            .connectionSpecs(listOf(ConnectionSpec.MODERN_TLS))
            .connectTimeout(conectaMs, TimeUnit.MILLISECONDS)
            .readTimeout(llamaMs, TimeUnit.MILLISECONDS)
            .writeTimeout(llamaMs, TimeUnit.MILLISECONDS)
            .callTimeout(llamaMs, TimeUnit.MILLISECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .retryOnConnectionFailure(false)
            .build()
    }
}
