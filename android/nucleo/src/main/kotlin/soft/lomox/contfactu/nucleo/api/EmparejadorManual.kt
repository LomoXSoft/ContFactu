// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo.api

import okhttp3.OkHttpClient
import soft.lomox.contfactu.nucleo.ConfirmacionInvalida
import soft.lomox.contfactu.nucleo.tls.Huellas
import soft.lomox.contfactu.nucleo.tls.PruebaEmparejar
import soft.lomox.contfactu.nucleo.tls.SondaTls
import soft.lomox.contfactu.nucleo.tls.TlsAnclado

/**
 * Emparejamiento sin QR. Ve el certificado, pide al PC que lo confirme y solo
 * entonces ancla esa huella y deja listo el cliente para enviar el código.
 */
class EmparejadorManual internal constructor(
    private val fabrica: (huella: String, host: String, llamaMs: Long) -> OkHttpClient,
) {
    constructor() : this({ huella, _, ms ->
        TlsAnclado.cliente(huella, conectaMs = minOf(3_000L, ms), llamaMs = ms)
    })
    fun preparar(host: String, puerto: Int, codigo: String): Preparado {
        val visto = SondaTls.certificado(host, puerto)
        val huella = Huellas.de(visto)
        val api = ClienteApi(fabrica(huella, host, 8_000), host, puerto, token = null)
        val recibida = api.confirmar(PruebaEmparejar.prueba(codigo, huella))
        val esperada = PruebaEmparejar.confirmacion(codigo, huella)
        if (!PruebaEmparejar.iguales(recibida, esperada)) {
            throw ConfirmacionInvalida()
        }
        return Preparado(api, huella)
    }

    data class Preparado(val api: ClienteApi, val huella: String)
}
