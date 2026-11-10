// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.nucleo.api

import okhttp3.OkHttpClient
import soft.lomox.contfactu.nucleo.AccesoApagado
import soft.lomox.contfactu.nucleo.ErrorContFactu
import soft.lomox.contfactu.nucleo.HuellaMalFormada
import soft.lomox.contfactu.nucleo.HuellaRechazada
import soft.lomox.contfactu.nucleo.PcInalcanzable
import soft.lomox.contfactu.nucleo.SinTls
import soft.lomox.contfactu.nucleo.tls.TlsAnclado

/**
 * Prueba las direcciones del QR en orden, con un tiempo corto en cada una.
 * La primera que completa TLS con la huella esperada y responde es la buena.
 * Si la huella no coincide se cierra esa conexión y no se envía el código ni el token.
 */
class Enlazador internal constructor(
    private val fabrica: (huella: String, host: String, llamaMs: Long) -> OkHttpClient,
) {
    constructor() : this({ huella, _, ms ->
        TlsAnclado.cliente(huella, conectaMs = minOf(3_000L, ms), llamaMs = ms)
    })
    fun abrir(hosts: List<String>, puerto: Int, huella: String, token: String?): ClienteApi {
        if (hosts.isEmpty()) {
            throw PcInalcanzable("No hay direcciones del PC.")
        }
        var huellaDistinta = false
        for (host in hosts) {
            val sonda = try {
                ClienteApi(fabrica(huella, host, SONDA_MS), host, puerto, token = null)
            } catch (e: HuellaMalFormada) {
                throw e
            }
            try {
                sonda.salud()
                return ClienteApi(fabrica(huella, host, USO_MS), host, puerto, token)
            } catch (e: HuellaRechazada) {
                huellaDistinta = true
            } catch (_: SinTls) {
                throw SinTls("La dirección no usa TLS. No se continúa.")
            } catch (e: AccesoApagado) {
                throw e
            } catch (_: PcInalcanzable) {
                // Esta dirección no contesta. Se prueba la siguiente.
            } catch (_: ErrorContFactu) {
                return ClienteApi(fabrica(huella, host, USO_MS), host, puerto, token)
            }
        }
        if (huellaDistinta) {
            throw HuellaRechazada("La huella del certificado no coincide. No se ha enviado nada.")
        }
        throw PcInalcanzable(
            "No se alcanza el PC en ${hosts.joinToString()}. " +
                "Puede estar apagado, con ContFactu cerrado, o el móvil fuera de su red. " +
                "Hace falta la misma wifi o la misma VPN.",
        )
    }

    companion object {
        const val SONDA_MS = 3_000L
        const val USO_MS = 30_000L
    }
}
