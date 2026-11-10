// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.ui.buscar

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import soft.lomox.contfactu.ContFactuApp
import soft.lomox.contfactu.nucleo.api.ResultadoBusqueda
import soft.lomox.contfactu.ui.Campo
import soft.lomox.contfactu.ui.Columna
import soft.lomox.contfactu.ui.EstadoCarga
import soft.lomox.contfactu.ui.EstadoError
import soft.lomox.contfactu.ui.EstadoVacio
import soft.lomox.contfactu.ui.etiquetaEstado
import soft.lomox.contfactu.ui.euros
import soft.lomox.contfactu.ui.fechaHumana
import soft.lomox.contfactu.ui.textoError

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BuscarPantalla(empresaId: Long, onFactura: (Long) -> Unit, onCliente: (Long) -> Unit) {
    val app = LocalContext.current.applicationContext as ContFactuApp
    var q by remember { mutableStateOf("") }
    var resultado by remember { mutableStateOf<ResultadoBusqueda?>(null) }
    var cargando by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(q, empresaId) {
        val texto = q.trim()
        resultado = null
        error = null
        if (texto.length < 2 && texto.toIntOrNull() == null) return@LaunchedEffect
        delay(280)
        cargando = true
        try {
            resultado = app.repositorio.usar { it.buscar(empresaId, texto) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = textoError(e)
        } finally {
            cargando = false
        }
    }
    Scaffold(topBar = { TopAppBar(title = { Text("Buscar") }) }) { padding ->
        Columna(Modifier.padding(padding).verticalScroll(rememberScrollState())) {
            Campo(q, { q = it }, "Clientes y facturas", ayuda = "Al menos dos caracteres, o un número.")
            when {
                cargando -> EstadoCarga("Consultando el PC…")
                error != null -> EstadoError(error!!)
                q.trim().length < 2 && q.trim().toIntOrNull() == null -> EstadoVacio("Escriba al menos dos caracteres, o un número.")
                resultado == null || resultado!!.total == 0 -> EstadoVacio("No hay resultados.")
                else -> {
                    val r = resultado!!
                    if (r.clientes.isNotEmpty()) {
                        Text("Clientes", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 8.dp))
                        r.clientes.forEach { cliente ->
                            Card(onClick = { onCliente(cliente.id) }, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                                Column(Modifier.padding(12.dp)) {
                                    Text(cliente.nombreF ?: cliente.nombre.orEmpty(), fontWeight = FontWeight.Medium)
                                    Text(listOfNotNull(cliente.nif, cliente.ciudad).joinToString(" · "), color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                    if (r.facturas.isNotEmpty()) {
                        Text("Facturas", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 12.dp))
                        r.facturas.forEach { factura ->
                            Card(onClick = { onFactura(factura.id) }, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                                Column(Modifier.padding(12.dp)) {
                                    Text(factura.numeroVisible ?: "Factura", fontWeight = FontWeight.Medium)
                                    Text(
                                        "${factura.nombreF.orEmpty()} · ${fechaHumana(factura.fecha)} · ${euros(factura.total)} · ${etiquetaEstado(factura.estado)}",
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
