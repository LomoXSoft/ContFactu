// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.ui

import soft.lomox.contfactu.nucleo.AccesoApagado
import soft.lomox.contfactu.nucleo.AccesoRevocado
import soft.lomox.contfactu.nucleo.CodigoInvalido
import soft.lomox.contfactu.nucleo.EmparejamientoBloqueado
import soft.lomox.contfactu.nucleo.HuellaMalFormada
import soft.lomox.contfactu.nucleo.HuellaRechazada
import soft.lomox.contfactu.nucleo.NoEncontrado
import soft.lomox.contfactu.nucleo.PcInalcanzable
import soft.lomox.contfactu.nucleo.PeticionRechazada
import soft.lomox.contfactu.nucleo.QrInvalido
import soft.lomox.contfactu.nucleo.RespuestaInesperada
import soft.lomox.contfactu.nucleo.SinSesion
import soft.lomox.contfactu.nucleo.SinTls
import soft.lomox.contfactu.nucleo.Validacion

fun textoError(e: Throwable): String = when (e) {
    is QrInvalido -> e.message ?: "El código QR no vale."
    is HuellaMalFormada -> "La huella no es un SHA-256 de 64 hexadecimales."
    is HuellaRechazada -> "La huella del certificado no coincide con la del PC. No se ha enviado el código ni el token."
    is SinTls -> "Esa dirección no usa TLS. ContFactu solo se atiende cifrado y esta aplicación se detiene."
    is AccesoApagado -> "Se ha llegado al PC, pero el acceso desde el móvil está apagado. Ábralo en Ajustes de ContFactu y vuelva a intentarlo."
    is AccesoRevocado -> "Este móvil ya no tiene acceso. En el PC se revocó el dispositivo, o el token ya no vale. Empareje de nuevo."
    is CodigoInvalido -> "El código es incorrecto, ha caducado o ya se ha usado."
    is soft.lomox.contfactu.nucleo.ConfirmacionInvalida -> e.message ?: "La confirmación del PC no coincide."
    is EmparejamientoBloqueado -> {
        val seg = e.reintentarEn.coerceAtLeast(0)
        val espera = when {
            seg >= 60 -> "${(seg + 59) / 60} min"
            seg > 0 -> "$seg s"
            else -> "un momento"
        }
        "Demasiados intentos. El emparejamiento está bloqueado. Puede reintentar dentro de $espera."
    }
    is NoEncontrado -> e.message ?: "No se ha encontrado en el PC."
    is PeticionRechazada -> e.message ?: "El PC ha rechazado la operación."
    is PcInalcanzable -> e.message ?: "No se alcanza el PC."
    is RespuestaInesperada -> e.message ?: "La respuesta del PC no se entiende."
    is SinSesion -> "Este móvil no está emparejado con ningún PC."
    is IllegalArgumentException -> e.message ?: "Revise los datos."
    else -> "No se ha podido completar la operación."
}

fun fechaHumana(iso: String?): String {
    if (iso.isNullOrBlank()) return ""
    val p = iso.split("-")
    return if (p.size == 3 && p[0].length == 4) "${p[2]}/${p[1]}/${p[0]}" else iso
}

fun euros(valor: String?): String {
    val t = Validacion.mostrar(valor)
    return if (t.isBlank()) "—" else "$t €"
}

fun etiquetaEstado(estado: String?): String = when (estado) {
    "cobrado" -> "Cobrado"
    "parcial" -> "Parcial"
    "pendiente" -> "Pendiente"
    null, "" -> ""
    else -> estado.replaceFirstChar { it.uppercase() }
}

fun hoyIso(): String = java.time.LocalDate.now().toString()
