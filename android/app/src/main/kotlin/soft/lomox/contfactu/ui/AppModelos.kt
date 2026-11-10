// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.ui

import android.app.Application
import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import soft.lomox.contfactu.ContFactuApp
import soft.lomox.contfactu.nucleo.api.Empresa
import soft.lomox.contfactu.nucleo.api.Sesion

sealed interface EstadoApp {
    data object Cargando : EstadoApp
    data object SinEmparejar : EstadoApp
    data class Listo(val sesion: Sesion) : EstadoApp
    data class SinEnlace(val sesion: Sesion, val mensaje: String) : EstadoApp
}

class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val aplicacion = app as ContFactuApp
    private val repo = aplicacion.repositorio
    private val cache = aplicacion.cachePdf

    var estado by mutableStateOf<EstadoApp>(EstadoApp.Cargando)
        private set
    var empresas by mutableStateOf<List<Empresa>>(emptyList())
        private set
    var empresaId by mutableStateOf<Long?>(null)

    val empresa: Empresa? get() = empresas.firstOrNull { it.id == empresaId }

    init {
        refrescar()
    }

    fun refrescar() {
        viewModelScope.launch {
            estado = EstadoApp.Cargando
            val sesion = repo.restaurar()
            if (sesion == null) {
                empresas = emptyList()
                empresaId = null
                estado = EstadoApp.SinEmparejar
                return@launch
            }
            try {
                val lista = repo.usar { it.empresas() }.empresas
                empresas = lista
                if (empresaId == null || lista.none { it.id == empresaId }) {
                    empresaId = lista.firstOrNull()?.id
                }
                estado = EstadoApp.Listo(sesion)
            } catch (e: Exception) {
                estado = EstadoApp.SinEnlace(sesion, textoError(e))
            }
        }
    }

    fun olvidar() {
        repo.olvidar()
        cache.borrar()
        empresas = emptyList()
        empresaId = null
        estado = EstadoApp.SinEmparejar
    }
}

class EmparejarViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = (app as ContFactuApp).repositorio
    var nombre by mutableStateOf(nombreDeEsteMovil())
    var ocupado by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)

    fun emparejar(qr: soft.lomox.contfactu.nucleo.qr.CodigoQr, alTerminar: () -> Unit) {
        if (ocupado) return
        lanzar(alTerminar) { repo.emparejar(qr, nombre) }
    }

    fun emparejarManual(destino: soft.lomox.contfactu.nucleo.qr.DestinoManual, alTerminar: () -> Unit) {
        if (ocupado) return
        lanzar(alTerminar) { repo.emparejarManual(destino, nombre) }
    }

    private fun lanzar(alTerminar: () -> Unit, bloque: suspend () -> Unit) {
        viewModelScope.launch {
            ocupado = true
            error = null
            try {
                bloque()
                alTerminar()
            } catch (e: Exception) {
                error = textoError(e)
            } finally {
                ocupado = false
            }
        }
    }
}

fun nombreDeEsteMovil(): String {
    val marca = Build.MANUFACTURER.orEmpty().trim()
    val modelo = Build.MODEL.orEmpty().trim()
    val junto = if (modelo.startsWith(marca, ignoreCase = true)) modelo else "$marca $modelo"
    return junto.filter { it.isLetterOrDigit() || it.isWhitespace() }.trim().take(60).ifBlank { "Dispositivo móvil" }
}
