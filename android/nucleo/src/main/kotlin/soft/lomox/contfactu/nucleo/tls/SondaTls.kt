// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo.tls

import soft.lomox.contfactu.nucleo.PcInalcanzable
import soft.lomox.contfactu.nucleo.SinTls
import java.net.InetSocketAddress
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocket
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * Abre TLS solo para ver el certificado. No envía HTTP, no ancla la huella
 * y no comprueba el nombre. Quien llama tiene que confirmar el HMAC antes de fiarse.
 */
object SondaTls {
    fun certificado(host: String, puerto: Int, timeoutMs: Int = 3_000): X509Certificate {
        val captura = CapturaCertificado()
        val contexto = SSLContext.getInstance("TLS")
        contexto.init(null, arrayOf<TrustManager>(captura), SecureRandom())
        val socket = contexto.socketFactory.createSocket() as SSLSocket
        try {
            socket.soTimeout = timeoutMs
            val parametros = socket.sslParameters
            parametros.endpointIdentificationAlgorithm = null
            socket.sslParameters = parametros
            val protocolos = arrayOf("TLSv1.3", "TLSv1.2").filter { it in socket.supportedProtocols }
            if (protocolos.isEmpty()) throw SinTls("Este equipo no ofrece TLS 1.2 o superior.")
            socket.enabledProtocols = protocolos.toTypedArray()
            socket.connect(InetSocketAddress(host, puerto), timeoutMs)
            socket.startHandshake()
            return captura.hoja ?: throw PcInalcanzable("El PC no ha presentado certificado.")
        } finally {
            try {
                socket.close()
            } catch (_: Exception) {
            }
        }
    }
}

/** Acepta el certificado solo para poder leerlo. No es un ancla. */
private class CapturaCertificado : X509TrustManager {
    var hoja: X509Certificate? = null

    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) = Unit

    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
        hoja = chain?.firstOrNull()
    }

    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
}
