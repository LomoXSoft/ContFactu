// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo

import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import soft.lomox.contfactu.nucleo.api.Enlazador
import soft.lomox.contfactu.nucleo.tls.AnclajeHuella
import soft.lomox.contfactu.nucleo.tls.Huellas
import soft.lomox.contfactu.nucleo.tls.TlsAnclado
import java.net.ConnectException
import java.util.concurrent.TimeUnit

class AnclajeHuellaTest {
    @Test
    fun el_trust_manager_acepta_la_huella_correcta_y_rechaza_otra() {
        val bueno = HeldCertificate.Builder().commonName("ContFactu").build()
        val malo = HeldCertificate.Builder().commonName("Otro").build()
        val anclaje = AnclajeHuella(Huellas.de(bueno.certificate).uppercase())
        anclaje.checkServerTrusted(arrayOf(bueno.certificate), "ECDHE_ECDSA")
        try {
            anclaje.checkServerTrusted(arrayOf(malo.certificate), "ECDHE_ECDSA")
            fail("tenía que rechazar el otro certificado")
        } catch (e: CertificadoNoAnclado) {
            assertTrue(e.message!!.contains("no coincide"))
        }
        try {
            anclaje.checkServerTrusted(emptyArray(), "ECDHE_ECDSA")
            fail("sin certificado no hay anclaje")
        } catch (e: CertificadoNoAnclado) {
            assertTrue(e.message!!.contains("no ha presentado"))
        }
    }

    @Test
    fun acepta_la_huella_correcta_en_una_conexion_tls() {
        val (server, huella) = servidorTls()
        server.use {
            server.enqueue(MockResponse().setBody("""{"nombre":"ContFactu","api":1,"version":"0.2.0"}"""))
            val cliente = TlsAnclado.cliente(huella, llamaMs = 3_000)
            val respuesta = cliente.newCall(
                Request.Builder().url(server.url("/api/v1/salud")).build(),
            ).execute()
            respuesta.use {
                assertEquals(200, it.code)
                assertTrue(it.body!!.string().contains("ContFactu"))
            }
            assertEquals(1, server.requestCount)
        }
    }

    @Test
    fun rechaza_otra_huella_y_no_envia_la_peticion() {
        val (server, _) = servidorTls()
        server.use {
            server.enqueue(MockResponse().setResponseCode(200).setBody("no deberia leerse"))
            val cliente = TlsAnclado.cliente("sha256:" + "ab".repeat(32), llamaMs = 3_000)
            try {
                cliente.newCall(Request.Builder().url(server.url("/api/v1/emparejar")).build()).execute()
                fail("tenía que rechazar el certificado")
            } catch (e: Exception) {
                assertTrue("causa=${e}", causaAnclaje(e))
            }
            assertNull(server.takeRequest(200, TimeUnit.MILLISECONDS))
            assertEquals(0, server.requestCount)
        }
    }

    @Test
    fun rechaza_una_conexion_sin_tls_y_no_envia_la_peticion() {
        val claro = MockWebServer()
        claro.start()
        claro.use {
            claro.enqueue(MockResponse().setBody("claro"))
            val cliente = TlsAnclado.cliente("sha256:" + "11".repeat(32), llamaMs = 3_000)
            try {
                cliente.newCall(Request.Builder().url(claro.url("/api/v1/salud")).build()).execute()
                fail("tenía que negarse a hablar sin TLS")
            } catch (e: Exception) {
                assertTrue(e is java.io.IOException)
            }
            assertNull(claro.takeRequest(200, TimeUnit.MILLISECONDS))
            assertEquals(0, claro.requestCount)
        }
    }

    @Test
    fun si_la_primera_direccion_no_contesta_prueba_la_siguiente() {
        val (server, huella) = servidorTls()
        server.use {
            server.enqueue(MockResponse().setBody("""{"nombre":"ContFactu","api":1,"version":"0.2.0"}"""))
            server.enqueue(MockResponse().setBody("""{"nombre":"ContFactu","api":1,"version":"0.2.0"}"""))
            val enlazador = Enlazador { h, host, ms ->
                val base = TlsAnclado.cliente(h, llamaMs = ms)
                if (host == "10.255.255.1") {
                    base.newBuilder().addInterceptor { throw ConnectException("apagado") }.build()
                } else {
                    base
                }
            }
            val api = enlazador.abrir(listOf("10.255.255.1", server.hostName), server.port, huella, null)
            assertEquals(server.hostName, api.host)
            assertEquals("ContFactu", api.salud().nombre)
            assertEquals(2, server.requestCount)
        }
    }

    @Test
    fun una_huella_ajena_no_envia_nada() {
        val (server, _) = servidorTls()
        server.use {
            val enlazador = Enlazador { h, _, ms -> TlsAnclado.cliente(h, llamaMs = ms) }
            try {
                enlazador.abrir(listOf(server.hostName), server.port, "sha256:" + "cd".repeat(32), null)
                fail("tenía que rechazar la huella")
            } catch (e: HuellaRechazada) {
                assertTrue(e.message!!.contains("No se ha enviado nada"))
            }
            assertEquals(0, server.requestCount)
        }
    }

    @Test(expected = HuellaMalFormada::class)
    fun rechaza_anclar_una_huella_mal_formada() {
        AnclajeHuella("sha256:no")
    }
}

private fun causaAnclaje(e: Throwable): Boolean {
    var actual: Throwable? = e
    while (actual != null) {
        if (actual is CertificadoNoAnclado) return true
        actual = actual.cause
    }
    return false
}

private fun servidorTls(): Pair<MockWebServer, String> {
    val cert = HeldCertificate.Builder()
        .commonName("ContFactu")
        .addSubjectAlternativeName("127.0.0.1")
        .build()
    val hs = HandshakeCertificates.Builder().heldCertificate(cert).build()
    val server = MockWebServer()
    server.useHttps(hs.sslSocketFactory(), false)
    server.start()
    return server to Huellas.de(cert.certificate)
}
