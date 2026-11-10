// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.ui.clientes

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import soft.lomox.contfactu.nucleo.api.Cliente
import soft.lomox.contfactu.ui.Campo
import soft.lomox.contfactu.ui.Columna
import soft.lomox.contfactu.ui.EstadoCarga
import soft.lomox.contfactu.ui.EstadoError
import soft.lomox.contfactu.ui.EstadoVacio
import soft.lomox.contfactu.ui.FilaDato
import soft.lomox.contfactu.ui.textoError

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ClientesPantalla(empresaId: Long, onAbrir: (Long) -> Unit) {
    val app = LocalContext.current.applicationContext as ContFactuApp
    var q by remember { mutableStateOf("") }
    var clientes by remember { mutableStateOf<List<Cliente>>(emptyList()) }
    var cargando by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var tick by remember { mutableStateOf(0) }
    LaunchedEffect(q, tick, empresaId) {
        delay(280)
        cargando = true
        try {
            clientes = app.repositorio.usar { it.clientes(empresaId, q = q.trim().ifBlank { null }) }.clientes
            error = null
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = textoError(e)
        } finally {
            cargando = false
        }
    }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Clientes") },
                actions = { TextButton(onClick = { tick++ }) { Text("Actualizar") } },
            )
        },
    ) { padding ->
        Columna(Modifier.padding(padding)) {
            Campo(q, { q = it }, "Buscar por nombre, NIF o código")
            when {
                cargando && clientes.isEmpty() -> EstadoCarga("Consultando el PC…")
                error != null && clientes.isEmpty() -> EstadoError(error!!, onReintentar = { tick++ })
                clientes.isEmpty() -> EstadoVacio("No hay clientes que coincidan.")
                else -> LazyColumn {
                    items(clientes, key = { it.id }) { cliente ->
                        Card(onClick = { onAbrir(cliente.id) }, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                            Column(Modifier.padding(14.dp)) {
                                Text(cliente.nombreF ?: cliente.nombre.orEmpty(), fontWeight = FontWeight.Medium)
                                val extra = listOfNotNull(cliente.codigo, cliente.nif, cliente.ciudad).joinToString(" · ")
                                if (extra.isNotBlank()) {
                                    Text(extra, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ClienteDetallePantalla(empresaId: Long, clienteId: Long, onAtras: () -> Unit) {
    val app = LocalContext.current.applicationContext as ContFactuApp
    var cliente by remember { mutableStateOf<Cliente?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var cargando by remember { mutableStateOf(true) }
    LaunchedEffect(clienteId, cargando) {
        if (!cargando) return@LaunchedEffect
        try {
            cliente = app.repositorio.usar { it.cliente(empresaId, clienteId) }
            error = null
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = textoError(e)
        } finally {
            cargando = false
        }
    }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text(cliente?.nombreF ?: cliente?.nombre ?: "Cliente") },
            navigationIcon = { IconButton(onClick = onAtras) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Volver") } },
        )
    }) { padding ->
        when {
            cargando && cliente == null -> EstadoCarga("Consultando el PC…")
            error != null && cliente == null -> EstadoError(error!!, onReintentar = { cargando = true })
            cliente != null -> Columna(Modifier.padding(padding).verticalScroll(rememberScrollState())) {
                val c = cliente!!
                FilaDato("Código", c.codigo)
                FilaDato("Nombre", c.nombre)
                FilaDato("Nombre fiscal", c.nombreF)
                FilaDato("NIF", c.nif)
                FilaDato("Dirección", c.direccionF ?: c.direccion)
                FilaDato("Ciudad", c.ciudadF ?: c.ciudad)
                FilaDato("Teléfono", c.telefono)
                FilaDato("Móvil", c.movil)
                FilaDato("Correo", c.email)
                FilaDato("Contacto", c.contacto)
                FilaDato("Forma de pago", c.formaPago)
                FilaDato("Días de pago", c.diasPago)
                FilaDato("Descuento", c.descuento)
                FilaDato("Recargo de equivalencia", if (c.recargo == "1") "Sí" else if (c.recargo == "0") "No" else c.recargo)
                FilaDato("Retiene", if (c.retiene == "1") "Sí" else if (c.retiene == "0") "No" else c.retiene)
            }
        }
    }
}
