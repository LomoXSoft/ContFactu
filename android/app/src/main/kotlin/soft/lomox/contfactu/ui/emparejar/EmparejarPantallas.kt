// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.ui.emparejar

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import soft.lomox.contfactu.R
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.zxing.BinaryBitmap
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader
import soft.lomox.contfactu.nucleo.qr.AnalizadorQr
import soft.lomox.contfactu.nucleo.qr.DestinoManual
import soft.lomox.contfactu.ui.Aviso
import soft.lomox.contfactu.ui.BotonSecundario
import soft.lomox.contfactu.ui.BotonTexto
import soft.lomox.contfactu.ui.Campo
import soft.lomox.contfactu.ui.Columna
import soft.lomox.contfactu.ui.EstadoCarga
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EmparejarPantalla(
    nombre: String,
    onNombre: (String) -> Unit,
    ocupado: Boolean,
    error: String?,
    onEscanear: () -> Unit,
    onManual: () -> Unit,
) {
    if (ocupado) {
        EstadoCarga("Comprobando la huella y el código…")
        return
    }
    Scaffold(topBar = { TopAppBar(title = { Text("Emparejar con el PC") }) }) { padding ->
        Columna(Modifier.padding(padding).verticalScroll(rememberScrollState())) {
            Text(
                "Los datos se quedan en el PC. Este móvil solo consulta y edita mientras ContFactu está abierto.",
                style = MaterialTheme.typography.bodyLarge,
            )
            Spacer(Modifier.height(16.dp))
            Campo(
                nombre,
                onNombre,
                "Nombre de este móvil",
                ayuda = "Es el nombre que verá en la lista de dispositivos del PC.",
            )
            Spacer(Modifier.height(12.dp))
            BotonTexto("Escanear código QR", Icons.Filled.QrCodeScanner, onClick = onEscanear)
            Spacer(Modifier.height(8.dp))
            BotonSecundario("Escribir el código", Icons.Filled.Edit, onClick = onManual)
            if (error != null) Aviso(error)
            Spacer(Modifier.height(28.dp))
            Text(
                "${stringResource(R.string.app_name)} · LomoXSoft · GPL v3",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ManualPantalla(
    ocupado: Boolean,
    error: String?,
    onAtras: () -> Unit,
    onDestino: (DestinoManual) -> Unit,
) {
    var codigo by remember { mutableStateOf("") }
    var direccion by remember { mutableStateOf("") }
    var puerto by remember { mutableStateOf("8766") }
    var local by remember { mutableStateOf<String?>(null) }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Código de respaldo") },
                navigationIcon = { androidx.compose.material3.TextButton(onClick = onAtras) { Text("Volver") } },
            )
        },
    ) { padding ->
        Columna(Modifier.padding(padding).verticalScroll(rememberScrollState())) {
            Text("Escriba la dirección del PC y el código que enseña ContFactu. La huella no se teclea: se comprueba con el PC antes de guardarla.")
            Spacer(Modifier.height(12.dp))
            Campo(direccion, { direccion = it }, "Dirección del PC", ayuda = "IP o nombre. Una sola.")
            Campo(puerto, { puerto = it }, "Puerto", ayuda = "Si el PC no dice otro, deje 8766.")
            Campo(codigo, { codigo = it }, "Código", ayuda = "Ocho caracteres, por ejemplo AB12-CD34.")
            Spacer(Modifier.height(8.dp))
            BotonTexto(
                if (ocupado) "Comprobando…" else "Emparejar",
                Icons.Filled.QrCodeScanner,
                enabled = !ocupado,
            ) {
                try {
                    local = null
                    onDestino(AnalizadorQr.manual(codigo, direccion, puerto))
                } catch (e: Exception) {
                    local = soft.lomox.contfactu.ui.textoError(e)
                }
            }
            if (local != null) Aviso(local!!)
            if (error != null) Aviso(error)
        }
    }
}

@Composable
fun EscanerPantalla(onTexto: (String) -> Unit, onAtras: () -> Unit, onManual: () -> Unit) {
    val contexto = LocalContext.current
    var concedido by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(contexto, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val pedir = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { concedido = it }
    androidx.compose.runtime.LaunchedEffect(Unit) {
        if (!concedido) pedir.launch(Manifest.permission.CAMERA)
    }
    if (!concedido) {
        Columna {
            Spacer(Modifier.height(24.dp))
            Text("Hace falta la cámara para leer el QR.", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            Text("El permiso solo sirve para eso. También puede escribir el código de respaldo.")
            Spacer(Modifier.height(16.dp))
            BotonTexto("Permitir la cámara", Icons.Filled.QrCodeScanner) { pedir.launch(Manifest.permission.CAMERA) }
            Spacer(Modifier.height(8.dp))
            BotonSecundario("Abrir ajustes del sistema", Icons.Filled.Edit) {
                val intent = Intent(
                    Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.fromParts("package", contexto.packageName, null),
                )
                contexto.startActivity(intent)
            }
            Spacer(Modifier.height(8.dp))
            BotonSecundario("Escribir el código", Icons.Filled.Edit, onClick = onManual)
            androidx.compose.material3.TextButton(onClick = onAtras) { Text("Volver") }
        }
        return
    }
    val entregado = remember { AtomicBoolean(false) }
    val ciclo = LocalLifecycleOwner.current
    val ejecutor = remember { Executors.newSingleThreadExecutor() }
    DisposableEffect(Unit) { onDispose { ejecutor.shutdown() } }
    Box(Modifier.fillMaxSize()) {
    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { ctx ->
            val vista = PreviewView(ctx).apply { contentDescription = "Cámara para el código QR" }
            val futuro = ProcessCameraProvider.getInstance(ctx)
            futuro.addListener({
                val proveedor = futuro.get()
                val preview = Preview.Builder().build().also { it.surfaceProvider = vista.surfaceProvider }
                val analisis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                analisis.setAnalyzer(ejecutor) { imagen ->
                    try {
                        if (!entregado.get()) {
                            val texto = decodificarQr(imagen)
                            if (texto != null && entregado.compareAndSet(false, true)) {
                                vista.post { onTexto(texto) }
                            }
                        }
                    } catch (_: Exception) {
                    } finally {
                        imagen.close()
                    }
                }
                try {
                    proveedor.unbindAll()
                    val selector = if (proveedor.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA)) {
                        CameraSelector.DEFAULT_BACK_CAMERA
                    } else {
                        CameraSelector.DEFAULT_FRONT_CAMERA
                    }
                    proveedor.bindToLifecycle(ciclo, selector, preview, analisis)
                } catch (_: Exception) {
                }
            }, ContextCompat.getMainExecutor(ctx))
            vista
        },
    )
        Button(onClick = onAtras, modifier = Modifier.align(Alignment.BottomCenter).padding(24.dp)) {
            Text("Volver")
        }
    }
}

private fun decodificarQr(imagen: androidx.camera.core.ImageProxy): String? {
    val plano = imagen.planes.firstOrNull() ?: return null
    val buffer = plano.buffer
    val datos = ByteArray(buffer.remaining())
    buffer.get(datos)
    val ancho = plano.rowStride.coerceAtLeast(imagen.width)
    if (ancho <= 0 || imagen.height <= 0 || datos.isEmpty()) return null
    val fuente = try {
        PlanarYUVLuminanceSource(datos, ancho, imagen.height, 0, 0, imagen.width, imagen.height, false)
    } catch (_: Exception) {
        return null
    }
    return leerQr(fuente) ?: leerQr(fuente.invert())
}

private fun leerQr(fuente: com.google.zxing.LuminanceSource): String? = try {
    QRCodeReader().decode(BinaryBitmap(HybridBinarizer(fuente))).text
} catch (_: Exception) {
    null
}
