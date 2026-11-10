// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.ui.ajustes

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.LinkOff
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import soft.lomox.contfactu.R
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import soft.lomox.contfactu.ContFactuApp
import soft.lomox.contfactu.nucleo.api.Sesion
import soft.lomox.contfactu.ui.Aviso
import soft.lomox.contfactu.ui.BotonSecundario
import soft.lomox.contfactu.ui.BotonTexto
import soft.lomox.contfactu.ui.Columna
import soft.lomox.contfactu.ui.FilaDato
import soft.lomox.contfactu.ui.textoError

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AjustesPantalla(sesion: Sesion?, empresa: String?, onOlvidar: () -> Unit, onLicencia: () -> Unit) {
    val app = LocalContext.current.applicationContext as ContFactuApp
    val ambito = rememberCoroutineScope()
    var comprobando by remember { mutableStateOf(false) }
    var mensaje by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmar by remember { mutableStateOf(false) }
    Scaffold(topBar = { TopAppBar(title = { Text("Ajustes") }) }) { padding ->
        Columna(Modifier.padding(padding).verticalScroll(rememberScrollState())) {
            Text("Conexión", style = MaterialTheme.typography.titleMedium)
            FilaDato("Dispositivo", sesion?.nombre)
            FilaDato("Direcciones", sesion?.hosts?.joinToString())
            FilaDato("Puerto", sesion?.puerto?.toString())
            FilaDato("Huella", sesion?.huella?.let { abreviar(it) })
            FilaDato("Empresa abierta", empresa)
            Spacer(Modifier.height(12.dp))
            BotonTexto(if (comprobando) "Comprobando…" else "Comprobar el PC", Icons.Filled.Refresh, enabled = !comprobando) {
                comprobando = true
                error = null
                mensaje = null
                ambito.launch {
                    try {
                        val salud = app.repositorio.usar { it.salud() }
                        mensaje = "ContFactu ${salud.version} responde. API ${salud.api}."
                    } catch (e: Exception) {
                        error = textoError(e)
                    } finally {
                        comprobando = false
                    }
                }
            }
            if (mensaje != null) {
                Text(mensaje!!, modifier = Modifier.padding(top = 8.dp), color = MaterialTheme.colorScheme.primary)
            }
            if (error != null) Aviso(error!!)
            Spacer(Modifier.height(20.dp))
            Text(
                "En este móvil solo está el token, cifrado con el almacén de claves de Android. Las facturas, los clientes y los PDF no se guardan.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(16.dp))
            BotonSecundario("Olvidar este PC", Icons.Filled.LinkOff) { confirmar = true }
            Spacer(Modifier.height(8.dp))
            TextButton(onClick = onLicencia) { Text("Licencia GPL v3") }
            Spacer(Modifier.height(12.dp))
            Text(stringResource(R.string.app_name), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("LomoXSoft", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    if (confirmar) {
        AlertDialog(
            onDismissRequest = { confirmar = false },
            title = { Text("Olvidar este PC") },
            text = { Text("Se borrará el token y la huella de este móvil. Los datos del PC no se tocan. Para volver a entrar hay que emparejar de nuevo.") },
            confirmButton = {
                TextButton(onClick = { confirmar = false; onOlvidar() }) { Text("Olvidar el PC") }
            },
            dismissButton = { TextButton(onClick = { confirmar = false }) { Text("Cancelar") } },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LicenciaPantalla(onAtras: () -> Unit) {
    val contexto = LocalContext.current
    val texto = remember {
        contexto.assets.open("LICENSE").bufferedReader().use { it.readText() }
    }
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("Licencia") },
            navigationIcon = { IconButton(onClick = onAtras) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Volver") } },
        )
    }) { padding ->
        Columna(Modifier.padding(padding).verticalScroll(rememberScrollState())) {
            Text("ContFactu para Android es software libre: GPL v3.", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            Text(texto, style = MaterialTheme.typography.bodySmall)
        }
    }
}

private fun abreviar(huella: String): String {
    if (huella.length < 20) return huella
    return huella.take(15) + "…" + huella.takeLast(8)
}
