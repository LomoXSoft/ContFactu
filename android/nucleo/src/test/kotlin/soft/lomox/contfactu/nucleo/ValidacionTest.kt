// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ValidacionTest {
    @Test
    fun el_iva_vacio_lo_decide_el_pc_y_el_resto_queda_en_texto() {
        assertTrue(Validacion.iva("") is ResultadoIva.Vacio)
        assertTrue(Validacion.iva("  ") is ResultadoIva.Vacio)
        assertEquals("7.5", (Validacion.iva("7,5") as ResultadoIva.Valido).texto)
        assertEquals("21", (Validacion.iva("21%") as ResultadoIva.Valido).texto)
        assertEquals("5.25", (Validacion.iva("5.250") as ResultadoIva.Valido).texto)
        assertEquals("7.555", (Validacion.iva("7.555") as ResultadoIva.Valido).texto)
        assertEquals("0", (Validacion.iva("0") as ResultadoIva.Valido).texto)
        assertEquals("100", (Validacion.iva("100") as ResultadoIva.Valido).texto)
        assertTrue(Validacion.iva("150") is ResultadoIva.Invalido)
        assertTrue(Validacion.iva("-1") is ResultadoIva.Invalido)
        assertEquals("0", (Validacion.descuento("") as ResultadoPorcentaje.Valido).texto)
        assertEquals("7.5", (Validacion.descuento("7,5") as ResultadoPorcentaje.Valido).texto)
        assertTrue(Validacion.descuento("150") is ResultadoPorcentaje.Invalido)
        assertTrue(Validacion.recargo("-1") is ResultadoPorcentaje.Invalido)
        assertEquals("5.2", (Validacion.recargo("5.2%") as ResultadoPorcentaje.Valido).texto)
        assertEquals("121", Validacion.importe("121,00", "Precio"))
        assertEquals("228,50", Validacion.mostrar("228.50"))
    }
}
