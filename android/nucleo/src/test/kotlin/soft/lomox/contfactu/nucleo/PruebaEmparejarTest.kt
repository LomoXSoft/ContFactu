// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo

import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import soft.lomox.contfactu.nucleo.api.EmparejadorManual
import soft.lomox.contfactu.nucleo.tls.Huellas
import soft.lomox.contfactu.nucleo.tls.PruebaEmparejar

/**
 * Vectores fijos, calculados con el mismo HMAC que `app/movil.py` del PC
 * (`hmac.new(codigo_normalizado, prefijo + "\n" + huella_canonica, sha256)`).
 */
class PruebaEmparejarTest {
    private val huella = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    @Test
    fun los_vectores_coinciden_con_el_pc() {
        assertEquals(
            "3d770bfe61ab22c27ace75e186aa4c25c4efcfd32b303423bcd5171a93a3644b",
            PruebaEmparejar.prueba("AB12-CD34", huella),
        )
        assertEquals(
            "138479ad59c9bc683ed039bdd8d623d31a179217ed2651daec771ff00905edeb",
            PruebaEmparejar.confirmacion("AB12-CD34", huella),
        )
        assertEquals(
            "532690a29cb4f2850ed008decdd2745c33987af02a17e74b6670bea5e3ef3012",
            PruebaEmparejar.prueba("ZZZZZZZZ", huella),
        )
    }

    @Test
    fun el_codigo_y_la_huella_se_normalizan_antes_del_hmac() {
        val conPuntos = "SHA256:" + huella.removePrefix("sha256:").chunked(2).joinToString(":")
        assertEquals(
            PruebaEmparejar.prueba("AB12-CD34", huella),
            PruebaEmparejar.prueba("  ab12 cd34 ", conPuntos),
        )
        assertTrue(PruebaEmparejar.iguales(
            PruebaEmparejar.confirmacion("AB12-CD34", huella).uppercase(),
            PruebaEmparejar.confirmacion("AB12CD34", huella),
        ))
        assertFalse(PruebaEmparejar.iguales(PruebaEmparejar.prueba("AB12-CD34", huella), "ab".repeat(32)))
        assertFalse(PruebaEmparejar.iguales("corta", PruebaEmparejar.prueba("AB12-CD34", huella)))
    }

    @Test
    fun si_la_confirmacion_cuadra_envia_el_codigo_y_si_no_no() {
        val (server, huellaReal) = servidor()
        server.use {
            val codigo = "AB12-CD34"
            server.dispatcher = object : Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    val cuerpo = request.body.readUtf8()
                    return when (request.path) {
                        "/api/v1/emparejar/confirmar" -> {
                            val prueba = PruebaEmparejar.prueba(codigo, huellaReal)
                            if (!cuerpo.contains(prueba) || cuerpo.contains(codigo)) {
                                return MockResponse().setResponseCode(401).setBody("""{"error":"no"}""")
                            }
                            MockResponse().setBody("""{"confirmacion":"${PruebaEmparejar.confirmacion(codigo, huellaReal)}"}""")
                        }
                        "/api/v1/emparejar" -> MockResponse().setBody(
                            """{"token":"secreto-de-prueba-32chars-min","dispositivo_id":4,"nombre":"Móvil"}""",
                        )
                        else -> MockResponse().setResponseCode(404)
                    }
                }
            }
            val preparado = EmparejadorManual().preparar(server.hostName, server.port, codigo)
            assertEquals(huellaReal, preparado.huella)
            val alta = preparado.api.emparejar(codigo, "Móvil")
            assertEquals(4L, alta.dispositivoId)
            assertEquals(2, server.requestCount)
        }
    }

    @Test
    fun una_confirmacion_falsa_no_ancla_ni_envia_el_codigo() {
        val (server, _) = servidor()
        server.use {
            server.enqueue(MockResponse().setBody("""{"confirmacion":"${"ab".repeat(32)}"}"""))
            try {
                EmparejadorManual().preparar(server.hostName, server.port, "AB12-CD34")
                fail("tenía que rechazar la confirmación")
            } catch (e: ConfirmacionInvalida) {
                assertTrue(e.message!!.contains("No se ha anclado"))
            }
            assertEquals(1, server.requestCount)
            assertEquals("/api/v1/emparejar/confirmar", server.takeRequest().path)
        }
    }

    @Test
    fun un_401_al_confirmar_dice_que_el_codigo_no_vale() {
        val (server, _) = servidor()
        server.use {
            server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":"El código no es válido o ha caducado."}"""))
            try {
                EmparejadorManual().preparar(server.hostName, server.port, "AB12-CD34")
                fail()
            } catch (_: CodigoInvalido) {
            }
            assertEquals(1, server.requestCount)
        }
    }
}

private fun servidor(): Pair<MockWebServer, String> {
    val cert = HeldCertificate.Builder().commonName("ContFactu").addSubjectAlternativeName("127.0.0.1").build()
    val hs = HandshakeCertificates.Builder().heldCertificate(cert).build()
    val server = MockWebServer()
    server.useHttps(hs.sslSocketFactory(), false)
    server.start()
    return server to Huellas.de(cert.certificate)
}
