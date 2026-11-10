// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import soft.lomox.contfactu.nucleo.qr.AnalizadorQr
import soft.lomox.contfactu.nucleo.qr.normalizarCodigo

class AnalizadorQrTest {
    private val huella = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    private val ejemplo = """
        {
          "v": 1,
          "app": "ContFactu",
          "hosts": ["192.168.1.20", "10.8.0.2", "100.64.1.5"],
          "puerto": 8766,
          "codigo": "AB12-CD34",
          "huella": "$huella"
        }
    """.trimIndent()

    @Test
    fun acepta_el_ejemplo_del_contrato_y_conserva_el_orden() {
        val qr = AnalizadorQr.analizar(ejemplo)
        assertEquals(listOf("192.168.1.20", "10.8.0.2", "100.64.1.5"), qr.hosts)
        assertEquals(8766, qr.puerto)
        assertEquals("AB12-CD34", qr.codigo)
        assertEquals(huella, qr.huella)
    }

    @Test
    fun el_orden_de_las_claves_no_importa() {
        val otro = """{"huella":"$huella","codigo":"AB12-CD34","puerto":8766,"hosts":["10.0.0.2"],"app":"ContFactu","v":1,"extra":true}"""
        val qr = AnalizadorQr.analizar(otro)
        assertEquals(listOf("10.0.0.2"), qr.hosts)
        assertEquals("AB12-CD34", qr.codigo)
    }

    @Test
    fun el_respaldo_pide_direccion_y_codigo_sin_huella() {
        val destino = AnalizadorQr.manual("  ab12 cd34 ", "pc.local", "8766")
        assertEquals("AB12-CD34", destino.codigo)
        assertEquals("pc.local", destino.host)
        assertEquals(8766, destino.puerto)
        val ip = AnalizadorQr.manual("AB12-CD34", "192.168.1.20", "")
        assertEquals("192.168.1.20", ip.host)
        assertEquals(8766, ip.puerto)
    }

    @Test
    fun el_codigo_sin_guion_tambien_vale() {
        assertEquals("AB12-CD34", normalizarCodigo("ab12cd34"))
        assertEquals("AB12-CD34", normalizarCodigo("AB12-CD34"))
    }

    @Test(expected = QrInvalido::class)
    fun rechaza_otra_version() {
        AnalizadorQr.analizar(ejemplo.replace("\"v\": 1", "\"v\": 2"))
    }

    @Test(expected = QrInvalido::class)
    fun rechaza_otra_aplicacion() {
        AnalizadorQr.analizar(ejemplo.replace("ContFactu", "Otra"))
    }

    @Test(expected = QrInvalido::class)
    fun rechaza_un_nombre_de_equipo() {
        AnalizadorQr.analizar(ejemplo.replace("192.168.1.20", "pc.local"))
    }

    @Test(expected = QrInvalido::class)
    fun rechaza_una_ipv4_imposible() {
        AnalizadorQr.analizar(ejemplo.replace("192.168.1.20", "192.168.1.256"))
    }

    @Test(expected = QrInvalido::class)
    fun rechaza_codigo_corto() {
        AnalizadorQr.manual("AB12", "192.168.0.1", "8766")
    }

    @Test(expected = QrInvalido::class)
    fun rechaza_una_direccion_con_esquema() {
        AnalizadorQr.manual("AB12-CD34", "https://192.168.0.1", "8766")
    }

    @Test(expected = QrInvalido::class)
    fun rechaza_texto_que_no_es_json() {
        AnalizadorQr.analizar("no-es-json")
    }

    @Test(expected = QrInvalido::class)
    fun rechaza_sin_direcciones() {
        AnalizadorQr.analizar(ejemplo.replace("""["192.168.1.20", "10.8.0.2", "100.64.1.5"]""", "[]"))
    }

    @Test
    fun el_puerto_vacio_del_respaldo_usa_8766() {
        val destino = AnalizadorQr.manual("AB12-CD34", "192.168.1.20", "  ")
        assertEquals(8766, destino.puerto)
    }
}
