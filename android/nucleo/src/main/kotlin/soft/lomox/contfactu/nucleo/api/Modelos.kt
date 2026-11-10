// SPDX-License-Identifier: GPL-3.0-or-later
@file:OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)

package soft.lomox.contfactu.nucleo.api

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive

/**
 * Algunos campos de ficha (recargo, retiene) salen como número y el resto como
 * texto. Aquí se guardan siempre como texto, sin pasar por coma flotante.
 */
object TextoFlexible : KSerializer<String?> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("TextoFlexible", PrimitiveKind.STRING)

    override fun deserialize(decoder: Decoder): String? {
        val json = decoder as? JsonDecoder ?: return decoder.decodeString()
        return when (val el = json.decodeJsonElement()) {
            JsonNull -> null
            is JsonPrimitive -> if (el.isString) el.content else el.content
            else -> el.toString()
        }
    }

    override fun serialize(encoder: Encoder, value: String?) {
        if (value == null) encoder.encodeNull() else encoder.encodeString(value)
    }
}

@Serializable
data class Salud(
    val nombre: String,
    val api: Int,
    val version: String,
)

@Serializable
data class PeticionConfirmar(val prueba: String)

@Serializable
data class RespuestaConfirmar(val confirmacion: String)

@Serializable
data class PeticionEmparejar(
    val codigo: String,
    val nombre: String,
)

@Serializable
data class RespuestaEmparejar(
    val token: String,
    @kotlinx.serialization.SerialName("dispositivo_id") val dispositivoId: Long,
    val nombre: String,
)

@Serializable
data class Empresa(
    val id: Long,
    val codigo: String? = null,
    val nombre: String? = null,
    val nif: String? = null,
    val ivas: List<String> = emptyList(),
    @kotlinx.serialization.SerialName("re_tasas") val reTasas: Map<String, String> = emptyMap(),
    @kotlinx.serialization.SerialName("n_facturas") val nFacturas: Int = 0,
)

@Serializable
data class ListaEmpresas(val empresas: List<Empresa> = emptyList())

@Serializable
data class ResumenFactura(
    val id: Long,
    val numero: String? = null,
    val serie: String = "",
    @kotlinx.serialization.SerialName("numero_visible") val numeroVisible: String = "",
    val fecha: String? = null,
    @kotlinx.serialization.SerialName("nombre_f") val nombreF: String? = null,
    val nif: String? = null,
    val total: String? = null,
    val pendiente: String? = null,
    val estado: String? = null,
)

@Serializable
data class ListaFacturas(
    val anio: String = "",
    val anios: List<String> = emptyList(),
    val facturas: List<ResumenFactura> = emptyList(),
)

@Serializable
data class LineaFactura(
    val orden: Int? = null,
    val codigo: String = "",
    val concepto: String = "",
    val cantidad: String = "",
    val precio: String = "",
    val descuento: String = "0",
    val iva: String = "",
    val comentario: Boolean = false,
)

@Serializable
data class TramoIva(
    val base: String,
    val iva: String,
    val re: String,
)

@Serializable
data class Factura(
    val id: Long,
    val numero: String? = null,
    val serie: String = "",
    @kotlinx.serialization.SerialName("numero_visible") val numeroVisible: String = "",
    val fecha: String? = null,
    @kotlinx.serialization.SerialName("fecha_operacion") val fechaOperacion: String? = null,
    @kotlinx.serialization.SerialName("nombre_f") val nombreF: String? = null,
    @kotlinx.serialization.SerialName("direccion_f") val direccionF: String? = null,
    @kotlinx.serialization.SerialName("ciudad_f") val ciudadF: String? = null,
    val nif: String? = null,
    @kotlinx.serialization.SerialName("cliente_codigo") val clienteCodigo: String? = null,
    @kotlinx.serialization.SerialName("forma_pago") val formaPago: String? = null,
    val descuento: String = "0",
    val retencion: String = "0",
    val exento: Boolean = false,
    @kotlinx.serialization.SerialName("iva_incluido") val ivaIncluido: Boolean = false,
    val re: Boolean = false,
    val total: String? = null,
    val pendiente: String? = null,
    val estado: String? = null,
    val desglose: List<TramoIva> = emptyList(),
    val lineas: List<LineaFactura> = emptyList(),
)

@Serializable
data class LineaEnvio(
    val concepto: String,
    val cantidad: String? = null,
    val precio: String? = null,
    val descuento: String? = null,
    val iva: String? = null,
    val codigo: String? = null,
    val comentario: Boolean? = null,
)

@Serializable
data class FacturaEnvio(
    val fecha: String,
    val serie: String? = null,
    @kotlinx.serialization.SerialName("cliente_id") val clienteId: Long? = null,
    @kotlinx.serialization.SerialName("nombre_f") val nombreF: String? = null,
    @kotlinx.serialization.SerialName("direccion_f") val direccionF: String? = null,
    @kotlinx.serialization.SerialName("ciudad_f") val ciudadF: String? = null,
    val nif: String? = null,
    @kotlinx.serialization.SerialName("cliente_codigo") val clienteCodigo: String? = null,
    @kotlinx.serialization.SerialName("forma_pago") val formaPago: String? = null,
    val domiciliacion: String? = null,
    val ccc: String? = null,
    val descuento: String? = null,
    val retencion: String? = null,
    val re: Boolean = false,
    val exento: Boolean = false,
    @kotlinx.serialization.SerialName("iva_incluido") val ivaIncluido: Boolean = false,
    val lineas: List<LineaEnvio>,
)

@Serializable
data class Cliente(
    val id: Long,
    val codigo: String? = null,
    val nombre: String? = null,
    @kotlinx.serialization.SerialName("nombre_f") val nombreF: String? = null,
    val nif: String? = null,
    val direccion: String? = null,
    @kotlinx.serialization.SerialName("direccion_f") val direccionF: String? = null,
    val ciudad: String? = null,
    @kotlinx.serialization.SerialName("ciudad_f") val ciudadF: String? = null,
    val telefono: String? = null,
    val movil: String? = null,
    val email: String? = null,
    val contacto: String? = null,
    @kotlinx.serialization.SerialName("forma_pago") val formaPago: String? = null,
    @kotlinx.serialization.SerialName("dias_pago") val diasPago: String? = null,
    @kotlinx.serialization.Serializable(with = TextoFlexible::class) val descuento: String? = null,
    @kotlinx.serialization.Serializable(with = TextoFlexible::class) val recargo: String? = null,
    @kotlinx.serialization.Serializable(with = TextoFlexible::class) val retiene: String? = null,
    val ccc: String? = null,
    val bic: String? = null,
    val domiciliacion: String? = null,
)

@Serializable
data class ListaClientes(val clientes: List<Cliente> = emptyList())

@Serializable
data class ResumenBusquedaCliente(
    val id: Long,
    val codigo: String? = null,
    val nombre: String? = null,
    @kotlinx.serialization.SerialName("nombre_f") val nombreF: String? = null,
    val nif: String? = null,
    val ciudad: String? = null,
)

@Serializable
data class ResumenBusquedaFactura(
    val id: Long,
    @kotlinx.serialization.SerialName("numero_visible") val numeroVisible: String? = null,
    val fecha: String? = null,
    @kotlinx.serialization.SerialName("nombre_f") val nombreF: String? = null,
    val nif: String? = null,
    val total: String? = null,
    val pendiente: String? = null,
    val estado: String? = null,
)

@Serializable
data class ResultadoBusqueda(
    val q: String = "",
    val clientes: List<ResumenBusquedaCliente> = emptyList(),
    val facturas: List<ResumenBusquedaFactura> = emptyList(),
    val total: Int = 0,
)

@Serializable
data class Sesion(
    val token: String,
    val huella: String,
    val hosts: List<String>,
    val puerto: Int,
    val nombre: String,
    val dispositivoId: Long,
)
