// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo.api

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import soft.lomox.contfactu.nucleo.AccesoApagado
import soft.lomox.contfactu.nucleo.AccesoRevocado
import soft.lomox.contfactu.nucleo.CertificadoNoAnclado
import soft.lomox.contfactu.nucleo.CodigoInvalido
import soft.lomox.contfactu.nucleo.EmparejamientoBloqueado
import soft.lomox.contfactu.nucleo.ErrorContFactu
import soft.lomox.contfactu.nucleo.HuellaRechazada
import soft.lomox.contfactu.nucleo.NoEncontrado
import soft.lomox.contfactu.nucleo.PcInalcanzable
import soft.lomox.contfactu.nucleo.PeticionRechazada
import soft.lomox.contfactu.nucleo.RespuestaInesperada
import soft.lomox.contfactu.nucleo.SinTls
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException

/**
 * Cliente de `https://{host}:{puerto}/api/v1`. No guarda respuestas.
 * Los importes siguen siendo texto de punta a punta.
 */
class ClienteApi(
    private val http: OkHttpClient,
    val host: String,
    val puerto: Int,
    private val token: String?,
) {
    init {
        if (puerto !in 1..65535) throw RespuestaInesperada("Puerto no válido.")
    }

    private val origen: HttpUrl = "https://$host:$puerto/".toHttpUrl()

    fun conToken(nuevo: String): ClienteApi = ClienteApi(http, host, puerto, nuevo)

    fun salud(): Salud = pedir(get("salud"), setOf(200)) { json.decodeFromString(it) }

    fun confirmar(prueba: String): String {
        val cuerpo = json.encodeToString(PeticionConfirmar(prueba)).toRequestBody(JSON)
        val peticion = Request.Builder()
            .url(url("emparejar/confirmar"))
            .post(cuerpo)
            .header("Accept", "application/json")
            .header("User-Agent", AGENTE)
            .build()
        val respuesta = pedir(peticion, setOf(200)) { json.decodeFromString<RespuestaConfirmar>(it) }
        return respuesta.confirmacion
    }

    fun emparejar(codigo: String, nombre: String): RespuestaEmparejar {
        val cuerpo = json.encodeToString(PeticionEmparejar(codigo, nombre)).toRequestBody(JSON)
        val peticion = Request.Builder()
            .url(url("emparejar"))
            .post(cuerpo)
            .header("Accept", "application/json")
            .header("User-Agent", AGENTE)
            .build()
        return pedir(peticion, setOf(200)) { json.decodeFromString(it) }
    }

    fun empresas(): ListaEmpresas = pedir(get("empresas"), setOf(200)) { json.decodeFromString(it) }

    fun facturas(empresa: Long, anio: String? = null, q: String? = null, limite: Int? = null): ListaFacturas {
        val consulta = linkedMapOf<String, String?>()
        if (!anio.isNullOrBlank()) consulta["anio"] = anio
        if (!q.isNullOrBlank()) consulta["q"] = q
        if (limite != null) consulta["limite"] = limite.toString()
        return pedir(get("empresas/$empresa/facturas", consulta), setOf(200)) { json.decodeFromString(it) }
    }

    fun factura(empresa: Long, id: Long): Factura =
        pedir(get("empresas/$empresa/facturas/$id"), setOf(200)) { json.decodeFromString(it) }

    fun crearFactura(empresa: Long, datos: FacturaEnvio): Factura {
        val cuerpo = json.encodeToString(datos).toRequestBody(JSON)
        val peticion = Request.Builder().url(url("empresas/$empresa/facturas")).post(cuerpo).autenticar().build()
        return pedir(peticion, setOf(201, 200)) { json.decodeFromString(it) }
    }

    fun editarFactura(empresa: Long, id: Long, datos: FacturaEnvio): Factura {
        val cuerpo = json.encodeToString(datos).toRequestBody(JSON)
        val peticion = Request.Builder().url(url("empresas/$empresa/facturas/$id")).put(cuerpo).autenticar().build()
        return pedir(peticion, setOf(200)) { json.decodeFromString(it) }
    }

    fun pdf(empresa: Long, id: Long): ByteArray {
        val peticion = get("empresas/$empresa/facturas/$id/pdf")
        return ejecutar(peticion).use { resp ->
            val bytes = resp.body?.bytes() ?: ByteArray(0)
            val tipo = resp.header("Content-Type").orEmpty()
            if (resp.code == 200 && tipo.contains("pdf", ignoreCase = true)) return bytes
            val texto = bytes.toString(Charsets.UTF_8)
            throw traducirHttp(resp.code, texto)
        }
    }

    fun clientes(empresa: Long, q: String? = null, limite: Int? = null): ListaClientes {
        val consulta = linkedMapOf<String, String?>()
        if (!q.isNullOrBlank()) consulta["q"] = q
        if (limite != null) consulta["limite"] = limite.toString()
        return pedir(get("empresas/$empresa/clientes", consulta), setOf(200)) { json.decodeFromString(it) }
    }

    fun cliente(empresa: Long, id: Long): Cliente =
        pedir(get("empresas/$empresa/clientes/$id"), setOf(200)) { json.decodeFromString(it) }

    fun buscar(empresa: Long, q: String): ResultadoBusqueda =
        pedir(get("empresas/$empresa/buscar", linkedMapOf("q" to q)), setOf(200)) { json.decodeFromString(it) }

    private fun get(ruta: String, consulta: Map<String, String?> = emptyMap()): Request =
        Request.Builder().url(url(ruta, consulta)).get().autenticar().build()

    private fun url(ruta: String, consulta: Map<String, String?> = emptyMap()): HttpUrl {
        val builder = origen.newBuilder()
        "api/v1".split('/').forEach { builder.addPathSegment(it) }
        ruta.trim('/').split('/').filter { it.isNotEmpty() }.forEach { builder.addPathSegment(it) }
        consulta.forEach { (clave, valor) -> if (valor != null) builder.addQueryParameter(clave, valor) }
        val hecha = builder.build()
        if (hecha.scheme != "https") throw SinTls()
        return hecha
    }

    private fun Request.Builder.autenticar(): Request.Builder {
        header("Accept", "application/json")
        header("User-Agent", AGENTE)
        if (!token.isNullOrEmpty()) header("Authorization", "Bearer $token")
        return this
    }

    private fun <T> pedir(peticion: Request, esperados: Set<Int>, leer: (String) -> T): T {
        ejecutar(peticion).use { resp ->
            val texto = resp.body?.string().orEmpty()
            if (resp.code !in esperados) throw traducirHttp(resp.code, texto)
            if (resp.code in 300..399) throw RespuestaInesperada("El PC ha pedido una redirección y no se sigue.")
            return try {
                leer(texto)
            } catch (e: ErrorContFactu) {
                throw e
            } catch (_: Exception) {
                throw RespuestaInesperada("La respuesta del PC no tiene la forma esperada.")
            }
        }
    }

    private fun ejecutar(peticion: Request) = try {
        if (peticion.url.scheme != "https") throw SinTls()
        http.newCall(peticion).execute()
    } catch (e: ErrorContFactu) {
        throw e
    } catch (e: IOException) {
        throw traducirIo(e)
    }

    private fun causaAnclaje(t: Throwable?): Boolean {
        var actual = t
        while (actual != null) {
            if (actual is CertificadoNoAnclado) return true
            actual = actual.cause
        }
        return false
    }

    private fun traducirIo(e: IOException): ErrorContFactu {
        if (causaAnclaje(e)) return HuellaRechazada("La huella del certificado no coincide.")
        return when (e) {
            is SocketTimeoutException -> PcInalcanzable("El PC no responde a tiempo.")
            is ConnectException -> PcInalcanzable("El puerto no responde.")
            is UnknownHostException -> PcInalcanzable("No se resuelve la dirección del PC.")
            is SSLException -> PcInalcanzable("No se ha podido cerrar TLS con el PC.")
            else -> PcInalcanzable(e.message ?: "No se alcanza el PC.")
        }
    }

    private fun traducirHttp(codigo: Int, cuerpo: String): ErrorContFactu {
        val error = parseError(cuerpo)
        return when (codigo) {
            401 -> if (token.isNullOrEmpty()) {
                CodigoInvalido(error.mensaje.ifBlank { "El código es incorrecto, ha caducado o ya se ha usado." })
            } else {
                AccesoRevocado(error.mensaje.ifBlank { "Acceso no autorizado." })
            }
            429 -> EmparejamientoBloqueado(
                error.reintento ?: 0,
                error.mensaje.ifBlank { "Demasiados intentos." },
            )
            404 -> if (error.mensaje == "No disponible.") AccesoApagado(error.mensaje) else NoEncontrado(error.mensaje.ifBlank { "No encontrado." })
            in 300..399 -> RespuestaInesperada("El PC ha pedido una redirección y no se sigue.")
            else -> PeticionRechazada(
                codigo,
                error.mensaje.ifBlank { "El PC ha rechazado la petición." },
                campo = error.campo,
                indice = error.indice,
            )
        }
    }

    private fun parseError(cuerpo: String): CuerpoError {
        return try {
            val el = json.parseToJsonElement(cuerpo)
            if (el !is JsonObject) return CuerpoError(cuerpo.take(180), null, null, null)
            val msg = el["error"]?.jsonPrimitive?.contentOrNull ?: ""
            val re = (el["reintentar_en"] as? JsonPrimitive)?.intOrNull
            val campo = (el["campo"] as? JsonPrimitive)?.contentOrNull
            val indice = (el["indice"] as? JsonPrimitive)?.intOrNull
            CuerpoError(msg, re, campo, indice)
        } catch (_: Exception) {
            CuerpoError(cuerpo.take(180), null, null, null)
        }
    }

    private data class CuerpoError(
        val mensaje: String,
        val reintento: Int?,
        val campo: String?,
        val indice: Int?,
    )

    companion object {
        const val AGENTE = "ContFactu-Android/0.2.0"
        private val JSON = "application/json; charset=utf-8".toMediaType()
        val json: Json = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
            encodeDefaults = true
            coerceInputValues = true
        }

        fun sesionAJson(sesion: Sesion): String = json.encodeToString(sesion)
        fun sesionDesdeJson(texto: String): Sesion = json.decodeFromString(texto)
    }
}
