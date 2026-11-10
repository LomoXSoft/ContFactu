// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo

import java.math.BigDecimal

/** IVA libre por línea: vacío (el PC aplica 21), o un tipo entre 0 y 100, ambos incluidos. */
sealed class ResultadoIva {
    data object Vacio : ResultadoIva()
    data class Valido(val texto: String) : ResultadoIva()
    data class Invalido(val mensaje: String) : ResultadoIva()
}

sealed class ResultadoPorcentaje {
    data class Valido(val texto: String) : ResultadoPorcentaje()
    data class Invalido(val mensaje: String) : ResultadoPorcentaje()
}

object Validacion {
    private val CIEN = BigDecimal(100)
    private val CERO = BigDecimal.ZERO

    fun iva(texto: String): ResultadoIva = when (val r = porcentaje(texto, "El IVA", vacioEsCero = false)) {
        is ResultadoPorcentaje.Valido -> if (texto.esVacio()) ResultadoIva.Vacio else ResultadoIva.Valido(r.texto)
        is ResultadoPorcentaje.Invalido -> ResultadoIva.Invalido(r.mensaje)
    }

    /** Descuento en porcentaje. Vacío equivale a 0. Fuera de 0–100 no vale. */
    fun descuento(texto: String): ResultadoPorcentaje = porcentaje(texto, "El descuento", vacioEsCero = true)

    /** Recargo de equivalencia en porcentaje. Vacío equivale a 0. Fuera de 0–100 no vale. */
    fun recargo(texto: String): ResultadoPorcentaje = porcentaje(texto, "El recargo de equivalencia", vacioEsCero = true)

    /** Importe de pantalla (coma) a texto con punto, sin convertir a flotante. */
    fun importe(texto: String, etiqueta: String): String? {
        val x = texto.trim().replace(" ", "").replace(',', '.')
        if (x.isEmpty()) return null
        val d = try {
            BigDecimal(x)
        } catch (_: NumberFormatException) {
            throw IllegalArgumentException("$etiqueta no es un número.")
        }
        if (d.scale() > 6 && d.stripTrailingZeros().scale() > 6) {
            throw IllegalArgumentException("$etiqueta tiene demasiados decimales.")
        }
        return d.stripTrailingZeros().toPlainString()
    }

    fun mostrar(valor: String?): String {
        if (valor.isNullOrBlank()) return ""
        return valor.trim().replace('.', ',')
    }

    private fun porcentaje(texto: String, etiqueta: String, vacioEsCero: Boolean): ResultadoPorcentaje {
        if (texto.esVacio()) {
            return if (vacioEsCero) {
                ResultadoPorcentaje.Valido("0")
            } else {
                ResultadoPorcentaje.Valido("")
            }
        }
        val x = texto.limpio()
        val d = try {
            BigDecimal(x)
        } catch (_: NumberFormatException) {
            return ResultadoPorcentaje.Invalido("$etiqueta no es válido: «$texto». Escriba un número entre 0 y 100.")
        }
        if (d < CERO || d > CIEN) {
            return ResultadoPorcentaje.Invalido("$etiqueta debe estar entre 0 % y 100 %.")
        }
        return ResultadoPorcentaje.Valido(d.stripTrailingZeros().toPlainString())
    }

    private fun String.esVacio(): Boolean = limpio().isEmpty()

    private fun String.limpio(): String = trim().replace("%", "").replace(" ", "").replace(',', '.')
}
