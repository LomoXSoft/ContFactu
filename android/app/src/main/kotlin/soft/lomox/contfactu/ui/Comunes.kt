// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

@Composable
fun Columna(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier
            .fillMaxSize()
            .widthIn(max = 760.dp)
            .padding(horizontal = 20.dp, vertical = 8.dp),
        content = content,
    )
}

@Composable
fun Campo(
    valor: String,
    onCambio: (String) -> Unit,
    etiqueta: String,
    modifier: Modifier = Modifier,
    unaLinea: Boolean = true,
    ayuda: String? = null,
    error: String? = null,
) {
    OutlinedTextField(
        value = valor,
        onValueChange = onCambio,
        label = { Text(etiqueta) },
        isError = error != null,
        supportingText = {
            when {
                error != null -> Text(error)
                ayuda != null -> Text(ayuda)
            }
        },
        singleLine = unaLinea,
        modifier = modifier.fillMaxWidth(),
    )
}

@Composable
fun BotonTexto(
    texto: String,
    icono: ImageVector,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    Button(onClick = onClick, enabled = enabled, modifier = modifier.fillMaxWidth()) {
        Icon(icono, contentDescription = null)
        Text(texto, modifier = Modifier.padding(start = 8.dp))
    }
}

@Composable
fun BotonSecundario(
    texto: String,
    icono: ImageVector,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    OutlinedButton(onClick = onClick, modifier = modifier.fillMaxWidth()) {
        Icon(icono, contentDescription = null)
        Text(texto, modifier = Modifier.padding(start = 8.dp))
    }
}

@Composable
fun EstadoCarga(texto: String) {
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator()
        Text(texto, modifier = Modifier.padding(top = 16.dp), style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
fun EstadoVacio(texto: String) {
    Text(
        texto,
        modifier = Modifier.fillMaxWidth().padding(vertical = 28.dp),
        textAlign = TextAlign.Center,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
fun EstadoError(texto: String, onReintentar: (() -> Unit)? = null, onOlvidar: (() -> Unit)? = null) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(texto, style = MaterialTheme.typography.bodyLarge, textAlign = TextAlign.Center)
        if (onReintentar != null) {
            Button(onClick = onReintentar, modifier = Modifier.padding(top = 20.dp)) { Text("Reintentar") }
        }
        if (onOlvidar != null) {
            OutlinedButton(onClick = onOlvidar, modifier = Modifier.padding(top = 8.dp)) { Text("Olvidar el PC") }
        }
    }
}

@Composable
fun Aviso(texto: String) {
    Text(
        texto,
        color = MaterialTheme.colorScheme.error,
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
    )
}

@Composable
fun FilaDato(etiqueta: String, valor: String?) {
    if (valor.isNullOrBlank()) return
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(etiqueta, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(end = 12.dp))
        Text(valor, textAlign = TextAlign.End, modifier = Modifier.weight(1f))
    }
}
