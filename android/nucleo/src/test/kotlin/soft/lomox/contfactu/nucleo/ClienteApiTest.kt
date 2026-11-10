// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo

import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import soft.lomox.contfactu.nucleo.api.ClienteApi
import soft.lomox.contfactu.nucleo.api.FacturaEnvio
import soft.lomox.contfactu.nucleo.api.LineaEnvio
import soft.lomox.contfactu.nucleo.tls.TlsAnclado

class ClienteApiTest {
    @Test
    fun empareja_sin_token_y_luego_usa_bearer() {
        val (server, api) = apiNueva(token = null)
        server.use {
            server.enqueue(MockResponse().setBody("""{"token":"secreto-de-prueba-32chars-min","dispositivo_id":1,"nombre":"Pixel de casa"}"""))
            server.enqueue(MockResponse().setBody("""{"empresas":[{"id":1,"codigo":"00001","nombre":"Ejemplo SL","nif":"B00000000","ivas":["21","10","4","0"],"re_tasas":{"21":"5.2","10":"1.4"},"n_facturas":3}]}"""))
            val alta = api.emparejar("AB12-CD34", "Pixel de casa")
            assertEquals("secreto-de-prueba-32chars-min", alta.token)
            assertEquals(1L, alta.dispositivoId)
            val altaReq = server.takeRequest()
            assertEquals("/api/v1/emparejar", altaReq.path)
            assertNull(altaReq.getHeader("Authorization"))
            assertTrue(altaReq.body.readUtf8().contains(""""codigo":"AB12-CD34""""))

            val empresas = api.conToken(alta.token).empresas()
            assertEquals("Ejemplo SL", empresas.empresas.single().nombre)
            assertEquals(listOf("21", "10", "4", "0"), empresas.empresas.single().ivas)
            assertEquals("5.2", empresas.empresas.single().reTasas["21"])
            val req = server.takeRequest()
            assertEquals("Bearer secreto-de-prueba-32chars-min", req.getHeader("Authorization"))
        }
    }

    @Test
    fun los_importes_siguen_siendo_texto() {
        val (server, api) = apiNueva(token = "token-de-prueba-largo-0123456789")
        server.use {
            server.enqueue(
                MockResponse().setResponseCode(201).setBody(
                    """{"id":10,"numero":"260001","serie":"","numero_visible":"260001","fecha":"2026-11-10","nombre_f":"Cliente Uno SL","nif":"12345678Z","total":"121.00","pendiente":"121.00","estado":"pendiente","descuento":"0","retencion":"0","exento":false,"iva_incluido":false,"re":false,"desglose":[{"base":"100.00","iva":"7.5","re":"0"}],"lineas":[{"orden":1,"codigo":"","concepto":"Especial","cantidad":"1","precio":"100","descuento":"0","iva":"7.5","comentario":false}]}""",
                ),
            )
            val creada = api.crearFactura(
                1,
                FacturaEnvio(
                    fecha = "2026-11-10",
                    nombreF = "Cliente Uno SL",
                    nif = "12345678Z",
                    lineas = listOf(LineaEnvio(concepto = "Especial", cantidad = "1", precio = "100", iva = "7.5")),
                ),
            )
            assertEquals("121.00", creada.total)
            assertEquals("7.5", creada.lineas.single().iva)
            assertEquals("100.00", creada.desglose.single().base)
            val cuerpo = server.takeRequest().body.readUtf8()
            assertTrue(cuerpo.contains(""""iva":"7.5""""))
            assertFalse(cuerpo.contains(""""iva":7.5"""))
            assertTrue(cuerpo.contains(""""precio":"100""""))
        }
    }

    @Test
    fun lista_edita_pdf_clientes_y_busqueda() {
        val token = "token-de-prueba-largo-0123456789"
        val (server, api) = apiNueva(token)
        server.use {
            server.enqueue(MockResponse().setBody("""{"anio":"2026","anios":["2026","2025"],"facturas":[{"id":10,"numero":"260001","serie":"","numero_visible":"260001","fecha":"2026-11-10","nombre_f":"Cliente Uno SL","nif":"12345678Z","total":"228.50","pendiente":"228.50","estado":"pendiente"}]}"""))
            val lista = api.facturas(1, anio = "2026", q = "Uno", limite = 50)
            assertEquals("2026", lista.anio)
            assertEquals("228.50", lista.facturas.single().total)
            val listaReq = server.takeRequest()
            assertTrue(listaReq.path!!.startsWith("/api/v1/empresas/1/facturas?"))
            assertTrue(listaReq.path!!.contains("anio=2026"))
            assertTrue(listaReq.path!!.contains("limite=50"))

            server.enqueue(MockResponse().setBody("""{"id":10,"numero":"260001","serie":"A","numero_visible":"A-260001","fecha":"2026-11-10","total":"10.00","pendiente":"0","estado":"cobrado","descuento":"0","retencion":"0","exento":false,"iva_incluido":false,"re":true,"desglose":[],"lineas":[]}"""))
            val editada = api.editarFactura(1, 10, FacturaEnvio(fecha = "2026-11-10", nombreF = "Cliente Uno SL", re = true, lineas = listOf(LineaEnvio(concepto = "Nota", comentario = true))))
            assertEquals("cobrado", editada.estado)
            assertTrue(editada.re)
            assertEquals("PUT", server.takeRequest().method)

            val pdf = "%PDF-1.4 sintetico".toByteArray()
            server.enqueue(MockResponse().setBody(okio.Buffer().write(pdf)).setHeader("Content-Type", "application/pdf"))
            assertTrue(api.pdf(1, 10).contentEquals(pdf))

            server.enqueue(MockResponse().setBody("""{"clientes":[{"id":3,"codigo":"C1","nombre":"Cliente Uno","nombre_f":"Cliente Uno SL","nif":"12345678Z","ciudad":"Madrid","email":"cliente@example.com","recargo":1,"retiene":0,"descuento":null}]}"""))
            val cliente = api.clientes(1, q = "Uno").clientes.single()
            assertEquals("1", cliente.recargo)
            assertEquals("0", cliente.retiene)
            assertNull(cliente.descuento)

            server.enqueue(MockResponse().setBody("""{"q":"Cliente","clientes":[{"id":3,"codigo":"C1","nombre":"Cliente Uno","nombre_f":"Cliente Uno SL","nif":"12345678Z","ciudad":"Madrid"}],"facturas":[{"id":10,"numero_visible":"260001","fecha":"2026-11-10","nombre_f":"Cliente Uno SL","nif":"12345678Z","total":"228.50","pendiente":"228.50","estado":"pendiente"}],"total":2}"""))
            val busqueda = api.buscar(1, "Cliente")
            assertEquals(2, busqueda.total)
            assertEquals("228.50", busqueda.facturas.single().total)
            assertEquals(token, server.takeRequest().getHeader("Authorization")!!.removePrefix("Bearer "))
        }
    }

    @Test
    fun el_401_con_token_es_acceso_revocado_y_sin_token_es_el_codigo() {
        val (server, conToken) = apiNueva("token-de-prueba-largo-0123456789")
        server.use {
            server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":"Acceso no autorizado."}"""))
            try {
                conToken.empresas()
                fail()
            } catch (e: AccesoRevocado) {
                assertEquals("Acceso no autorizado.", e.message)
            }
            server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":"El código no es válido o ha caducado."}"""))
            try {
                conToken.conToken("").emparejar("XXXX-XXXX", "x")
                fail()
            } catch (_: CodigoInvalido) {
            }
        }
    }

    @Test
    fun el_429_trae_reintentar_en_y_el_404_apagado_se_distingue() {
        val (server, api) = apiNueva(null)
        server.use {
            server.enqueue(MockResponse().setResponseCode(429).setBody("""{"error":"Demasiados intentos. El emparejamiento está bloqueado un momento.","reintentar_en":900}"""))
            try {
                api.emparejar("AB12-CD34", "x")
                fail()
            } catch (e: EmparejamientoBloqueado) {
                assertEquals(900, e.reintentarEn)
            }
            server.enqueue(MockResponse().setResponseCode(404).setBody("""{"error":"No disponible."}"""))
            try {
                api.salud()
                fail()
            } catch (_: AccesoApagado) {
            }
            server.enqueue(MockResponse().setResponseCode(404).setBody("""{"error":"No encontrado."}"""))
            try {
                api.factura(1, 9)
                fail()
            } catch (_: NoEncontrado) {
            }
            server.enqueue(MockResponse().setResponseCode(400).setBody("""{"error":"El IVA debe estar entre 0 % y 100 %.","campo":"iva","indice":1}"""))
            try {
                api.crearFactura(1, FacturaEnvio(fecha = "2026-11-10", nombreF = "A", lineas = listOf(LineaEnvio(concepto = "A", precio = "1", iva = "150"))))
                fail()
            } catch (e: PeticionRechazada) {
                assertEquals(400, e.estado)
                assertEquals("iva", e.campo)
                assertEquals(1, e.indice)
                assertTrue(e.message!!.contains("100"))
            }
            server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":"El código no es válido o ha caducado."}"""))
            try {
                api.confirmar("ab".repeat(32))
                fail()
            } catch (_: CodigoInvalido) {
            }
        }
    }
}

private fun apiNueva(token: String?): Pair<MockWebServer, ClienteApi> {
    val cert = okhttp3.tls.HeldCertificate.Builder().commonName("ContFactu").build()
    val hs = okhttp3.tls.HandshakeCertificates.Builder().heldCertificate(cert).build()
    val server = MockWebServer()
    server.useHttps(hs.sslSocketFactory(), false)
    server.start()
    val huella = soft.lomox.contfactu.nucleo.tls.Huellas.de(cert.certificate)
    val http = TlsAnclado.cliente(huella, llamaMs = 3_000)
    return server to ClienteApi(http, server.hostName, server.port, token)
}
