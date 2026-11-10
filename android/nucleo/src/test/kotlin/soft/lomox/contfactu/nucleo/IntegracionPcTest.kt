// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import soft.lomox.contfactu.nucleo.api.EmparejadorManual
import soft.lomox.contfactu.nucleo.api.FacturaEnvio
import soft.lomox.contfactu.nucleo.api.LineaEnvio
import java.io.File

/**
 * Se ejecuta solo si hay un ContFactu de prueba escuchando.
 * El archivo lo escribe quien arranca el servidor con datos sintéticos:
 * `{"hosts":["127.0.0.1"],"puerto":8766,"codigo":"AB12-CD34","huella":"sha256:…"}`.
 */
class IntegracionPcTest {
    @Test
    fun contra_el_pc_con_datos_sinteticos() {
        val ruta = System.getenv("CONTFACTU_IT") ?: "/tmp/contfactu-it.json"
        val archivo = File(ruta)
        assumeTrue("No hay servidor de ContFactu en $ruta", archivo.isFile)
        val cfg = Json { ignoreUnknownKeys = true }.decodeFromString<CfgIt>(archivo.readText())
        val preparado = EmparejadorManual().preparar(cfg.hosts.first(), cfg.puerto, cfg.codigo)
        assertEquals(cfg.huella, preparado.huella)
        assertEquals("ContFactu", preparado.api.salud().nombre)
        val alta = preparado.api.emparejar(cfg.codigo, "Prueba sintética")
        assertTrue(alta.token.length >= 20)
        val api = preparado.api.conToken(alta.token)
        val empresas = api.empresas().empresas
        assertTrue(empresas.isNotEmpty())
        val id = empresas.first().id
        val creada = api.crearFactura(
            id,
            FacturaEnvio(
                fecha = "2026-11-10",
                nombreF = "Cliente Sintético SL",
                nif = "12345678Z",
                lineas = listOf(
                    LineaEnvio(concepto = "Tornillos", cantidad = "2", precio = "10.50", descuento = "0", iva = "21"),
                    LineaEnvio(concepto = "Especial", cantidad = "1", precio = "100", iva = "7.5"),
                    LineaEnvio(concepto = "Nota interna", comentario = true),
                ),
            ),
        )
        assertEquals("Cliente Sintético SL", creada.nombreF)
        assertTrue(creada.lineas.any { it.iva == "7.5" || it.iva == "7.50" })
        assertTrue(creada.total!!.isNotEmpty())
        val pdf = api.pdf(id, creada.id)
        assertTrue(pdf.size > 5)
        assertEquals('%'.code.toByte(), pdf[0])
        val busqueda = api.buscar(id, "Sintético")
        assertTrue(busqueda.facturas.any { it.id == creada.id } || busqueda.total >= 1)
        val clientes = api.clientes(id, q = "Sintético")
        assertTrue(clientes.clientes.isEmpty() || clientes.clientes.all { it.id > 0 })
        archivo.delete()
    }
}

@Serializable
private data class CfgIt(
    val hosts: List<String>,
    val puerto: Int,
    val codigo: String,
    val huella: String,
)
