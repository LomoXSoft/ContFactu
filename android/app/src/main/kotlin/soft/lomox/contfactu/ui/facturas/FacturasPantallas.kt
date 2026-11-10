// SPDX-License-Identifier: GPL-3.0-or-later

@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package soft.lomox.contfactu.ui.facturas

import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.PictureAsPdf
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Card
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import soft.lomox.contfactu.ContFactuApp
import soft.lomox.contfactu.nucleo.AccesoRevocado
import soft.lomox.contfactu.nucleo.PeticionRechazada
import soft.lomox.contfactu.nucleo.ResultadoIva
import soft.lomox.contfactu.nucleo.ResultadoPorcentaje
import soft.lomox.contfactu.nucleo.Validacion
import soft.lomox.contfactu.nucleo.api.Empresa
import soft.lomox.contfactu.nucleo.api.Factura
import soft.lomox.contfactu.nucleo.api.FacturaEnvio
import soft.lomox.contfactu.nucleo.api.LineaEnvio
import soft.lomox.contfactu.nucleo.api.ResumenFactura
import soft.lomox.contfactu.ui.Aviso
import soft.lomox.contfactu.ui.BotonSecundario
import soft.lomox.contfactu.ui.BotonTexto
import soft.lomox.contfactu.ui.Campo
import soft.lomox.contfactu.ui.Columna
import soft.lomox.contfactu.ui.EstadoCarga
import soft.lomox.contfactu.ui.EstadoError
import soft.lomox.contfactu.ui.EstadoVacio
import soft.lomox.contfactu.ui.FilaDato
import soft.lomox.contfactu.ui.etiquetaEstado
import soft.lomox.contfactu.ui.euros
import soft.lomox.contfactu.ui.fechaHumana
import soft.lomox.contfactu.ui.hoyIso
import soft.lomox.contfactu.ui.textoError
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FacturasPantalla(
    empresaId: Long?,
    empresas: List<Empresa>,
    onEmpresa: (Long) -> Unit,
    onAbrir: (Long) -> Unit,
    onNueva: () -> Unit,
) {
    if (empresaId == null) {
        EstadoVacio("El PC no tiene empresas.")
        return
    }
    val app = LocalContext.current.applicationContext as ContFactuApp
    val vm: FacturasViewModel = viewModel(
        key = "facturas-$empresaId",
        factory = fabrica { FacturasViewModel(app, empresaId) },
    )
    LaunchedEffect(empresaId) { vm.cargar() }
    var menu by remember { mutableStateOf(false) }
    val nombre = empresas.firstOrNull { it.id == empresaId }?.nombre ?: "Empresa"
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    TextButton(onClick = { if (empresas.size > 1) menu = true }) {
                        Text(nombre, style = MaterialTheme.typography.titleLarge)
                    }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        empresas.forEach { empresa ->
                            DropdownMenuItem(
                                text = { Text(empresa.nombre ?: "Empresa ${empresa.id}") },
                                onClick = {
                                    menu = false
                                    onEmpresa(empresa.id)
                                },
                            )
                        }
                    }
                },
                actions = {
                    TextButton(onClick = { vm.cargar() }) { Text("Actualizar") }
                },
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = onNueva, icon = { Icon(Icons.Filled.Add, null) }, text = { Text("Nueva factura") })
        },
    ) { padding ->
        Columna(Modifier.padding(padding)) {
            Campo(vm.q, { vm.q = it; vm.cargar() }, "Buscar por nombre, NIF o número", ayuda = null)
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                vm.anios.forEach { anio ->
                    FilterChip(selected = vm.anioVisible == anio, onClick = { vm.elegirAnio(anio) }, label = { Text(anio) })
                }
                if (vm.anios.isNotEmpty()) {
                    FilterChip(selected = vm.anioVisible == "todos", onClick = { vm.elegirAnio("todos") }, label = { Text("Todos") })
                }
            }
            when {
                vm.cargando && vm.facturas.isEmpty() -> EstadoCarga("Consultando el PC…")
                vm.error != null && vm.facturas.isEmpty() -> EstadoError(vm.error!!, onReintentar = { vm.cargar() })
                vm.facturas.isEmpty() -> EstadoVacio("No hay facturas en este año.")
                else -> LazyColumn(Modifier.fillMaxSize()) {
                    items(vm.facturas, key = { it.id }) { factura ->
                        TarjetaFactura(factura) { onAbrir(factura.id) }
                    }
                }
            }
            if (vm.error != null && vm.facturas.isNotEmpty()) Aviso(vm.error!!)
        }
    }
}

@Composable
private fun TarjetaFactura(factura: ResumenFactura, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Column(Modifier.padding(16.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(factura.numeroVisible.ifBlank { "Factura" }, fontWeight = FontWeight.SemiBold)
                Text(euros(factura.total), fontWeight = FontWeight.SemiBold)
            }
            Text(factura.nombreF.orEmpty(), modifier = Modifier.padding(top = 4.dp))
            Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(fechaHumana(factura.fecha), color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(etiquetaEstado(factura.estado), color = colorEstado(factura.estado))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DetalleFacturaPantalla(
    empresaId: Long,
    facturaId: Long,
    onEditar: () -> Unit,
    onPdf: () -> Unit,
    onAtras: () -> Unit,
    onRevocado: () -> Unit,
) {
    val app = LocalContext.current.applicationContext as ContFactuApp
    var factura by remember { mutableStateOf<Factura?>(null) }
    var cargando by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var revocado by remember { mutableStateOf(false) }
    fun cargar() {
        cargando = true
        error = null
    }
    LaunchedEffect(empresaId, facturaId, cargando) {
        if (!cargando) return@LaunchedEffect
        try {
            factura = app.repositorio.usar { it.factura(empresaId, facturaId) }
            error = null
        } catch (e: CancellationException) {
            throw e
        } catch (e: AccesoRevocado) {
            error = textoError(e)
            revocado = true
        } catch (e: Exception) {
            error = textoError(e)
        } finally {
            cargando = false
        }
    }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(factura?.numeroVisible ?: "Factura") },
                navigationIcon = {
                    IconButton(onClick = onAtras) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Volver") }
                },
            )
        },
    ) { padding ->
        when {
            cargando && factura == null -> EstadoCarga("Consultando el PC…")
            error != null && factura == null -> EstadoError(
                error!!,
                onReintentar = { cargando = true },
                onOlvidar = if (revocado) onRevocado else null,
            )
            factura != null -> Columna(Modifier.padding(padding).verticalScroll(rememberScrollState())) {
                val f = factura!!
                Text(f.nombreF.orEmpty(), style = MaterialTheme.typography.titleLarge)
                FilaDato("Fecha", fechaHumana(f.fecha))
                FilaDato("NIF", f.nif)
                FilaDato("Dirección", listOfNotNull(f.direccionF, f.ciudadF).filter { it.isNotBlank() }.joinToString(", ").ifBlank { null })
                FilaDato("Estado", etiquetaEstado(f.estado))
                FilaDato("Pendiente", euros(f.pendiente))
                Spacer(Modifier.height(12.dp))
                Text("Líneas", style = MaterialTheme.typography.titleMedium)
                f.lineas.forEach { linea ->
                    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                        Text(linea.concepto.ifBlank { "Sin concepto" })
                        if (!linea.comentario) {
                            Text(
                                "${Validacion.mostrar(linea.cantidad)} × ${euros(linea.precio)} · IVA ${Validacion.mostrar(linea.iva).ifBlank { "21" }}",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        } else {
                            Text("Comentario", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                if (f.desglose.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text("Desglose", style = MaterialTheme.typography.titleMedium)
                    f.desglose.forEach { tramo ->
                        FilaDato("Base ${Validacion.mostrar(tramo.iva)} %", euros(tramo.base))
                    }
                }
                FilaDato("Total", euros(f.total))
                Text("El total lo calcula el PC.", color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp))
                Spacer(Modifier.height(16.dp))
                BotonTexto("Editar", Icons.Filled.Edit, onClick = onEditar)
                Spacer(Modifier.height(8.dp))
                BotonSecundario("Ver PDF", Icons.Filled.PictureAsPdf, onClick = onPdf)
                if (error != null) Aviso(error!!)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditorFacturaPantalla(
    empresaId: Long,
    facturaId: Long?,
    ivaDefecto: String,
    onGuardada: (Long) -> Unit,
    onAtras: () -> Unit,
) {
    val app = LocalContext.current.applicationContext as ContFactuApp
    val creando = facturaId == null
    var borrador by remember {
        mutableStateOf(Borrador(fecha = hoyIso(), lineas = listOf(LineaEditable(iva = ivaDefecto))))
    }
    var cargando by remember { mutableStateOf(!creando) }
    var guardando by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var errorCampo by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var errorLinea by remember { mutableStateOf<Map<Int, Map<String, String>>>(emptyMap()) }
    var fechaAbierta by remember { mutableStateOf(false) }
    var eligiendo by remember { mutableStateOf(false) }
    var sucio by remember { mutableStateOf(false) }
    var confirmarSalida by remember { mutableStateOf(false) }

    LaunchedEffect(facturaId) {
        if (facturaId == null) return@LaunchedEffect
        try {
            val f = app.repositorio.usar { it.factura(empresaId, facturaId) }
            borrador = f.aBorrador()
        } catch (e: Exception) {
            error = textoError(e)
        } finally {
            cargando = false
        }
    }

    fun tocar(nuevo: Borrador) {
        borrador = nuevo
        sucio = true
    }

    BackHandler(sucio && !guardando) { confirmarSalida = true }

    if (eligiendo) {
        SelectorCliente(
            empresaId = empresaId,
            onCerrar = { eligiendo = false },
            onElegido = { cliente ->
                tocar(
                    borrador.copy(
                        clienteId = cliente.id,
                        nombre = borrador.nombre.ifBlank { cliente.nombreF ?: cliente.nombre.orEmpty() },
                        nif = borrador.nif.ifBlank { cliente.nif.orEmpty() },
                        direccion = borrador.direccion.ifBlank { cliente.direccionF ?: cliente.direccion.orEmpty() },
                        ciudad = borrador.ciudad.ifBlank { cliente.ciudadF ?: cliente.ciudad.orEmpty() },
                        codigoCliente = borrador.codigoCliente.ifBlank { cliente.codigo.orEmpty() },
                        formaPago = borrador.formaPago.ifBlank { cliente.formaPago.orEmpty() },
                        descuento = if (borrador.descuento.isBlank() || borrador.descuento == "0") cliente.descuento ?: borrador.descuento else borrador.descuento,
                    ),
                )
                eligiendo = false
            },
        )
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (creando) "Nueva factura" else "Editar factura") },
                navigationIcon = {
                    IconButton(onClick = { if (sucio) confirmarSalida = true else onAtras() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Volver")
                    }
                },
                actions = {
                    TextButton(
                        enabled = !guardando && !cargando,
                        onClick = {
                            guardando = true
                            error = null
                        },
                    ) { Text(if (guardando) "Guardando…" else "Guardar") }
                },
            )
        },
    ) { padding ->
        if (cargando) {
            EstadoCarga("Consultando el PC…")
            return@Scaffold
        }
        LaunchedEffect(guardando) {
            if (!guardando) return@LaunchedEffect
            try {
                val envio = borrador.aEnvio(creando)
                val guardada = app.repositorio.usar { api ->
                    if (creando) api.crearFactura(empresaId, envio) else api.editarFactura(empresaId, facturaId!!, envio)
                }
                sucio = false
                errorCampo = emptyMap()
                errorLinea = emptyMap()
                onGuardada(guardada.id)
            } catch (e: CancellationException) {
                throw e
            } catch (e: DatosFormulario) {
                errorCampo = e.campos
                errorLinea = e.lineas
                error = null
            } catch (e: PeticionRechazada) {
                val puesto = colocarErrorServidor(e)
                errorCampo = puesto.campos
                errorLinea = puesto.lineas
                error = if (puesto.aviso) e.message else null
            } catch (e: Exception) {
                error = textoError(e)
            } finally {
                guardando = false
            }
        }
        Columna(Modifier.padding(padding).verticalScroll(rememberScrollState())) {
            if (!creando && borrador.numero.isNotBlank()) {
                Text("Número ${borrador.numero}. Lo asigna el PC y no se puede cambiar.")
                Spacer(Modifier.height(8.dp))
            }
            TextButton(onClick = { fechaAbierta = true; errorCampo = errorCampo - "fecha" }) { Text("Fecha ${fechaHumana(borrador.fecha)}") }
            if (errorCampo["fecha"] != null) Aviso(errorCampo["fecha"]!!)
            if (errorCampo["cp"] != null) Aviso("Código postal: ${errorCampo["cp"]}")
            if (creando) {
                Campo(
                    borrador.serie,
                    { tocar(borrador.copy(serie = it.take(3))); errorCampo = errorCampo - "serie" },
                    "Serie",
                    ayuda = "Hasta 3 caracteres. Vacío, sin serie.",
                    error = errorCampo["serie"],
                )
            }
            BotonSecundario("Elegir cliente", Icons.Filled.Search) { eligiendo = true }
            Campo(borrador.nombre, { tocar(borrador.copy(nombre = it)); errorCampo = errorCampo - "nombre" }, "Nombre fiscal", error = errorCampo["nombre"])
            Campo(borrador.nif, { tocar(borrador.copy(nif = it)); errorCampo = errorCampo - "nif" }, "NIF", error = errorCampo["nif"])
            Campo(borrador.direccion, { tocar(borrador.copy(direccion = it)); errorCampo = errorCampo - "direccion" }, "Dirección", error = errorCampo["direccion"])
            Campo(borrador.ciudad, { tocar(borrador.copy(ciudad = it)); errorCampo = errorCampo - "ciudad" }, "Ciudad", error = errorCampo["ciudad"])
            Campo(borrador.codigoCliente, { tocar(borrador.copy(codigoCliente = it)); errorCampo = errorCampo - "codigo" }, "Código de cliente", error = errorCampo["codigo"])
            Campo(borrador.formaPago, { tocar(borrador.copy(formaPago = it)) }, "Forma de pago")
            Campo(
                borrador.descuento,
                { tocar(borrador.copy(descuento = it)); errorCampo = errorCampo - "descuento" },
                "Descuento general",
                ayuda = "Entre 0 y 100. Vacío equivale a 0.",
                error = errorCampo["descuento"],
            )
            Campo(
                borrador.retencion,
                { tocar(borrador.copy(retencion = it)); errorCampo = errorCampo - "retencion" },
                "Retención",
                error = errorCampo["retencion"],
            )
            Interruptor("Recargo de equivalencia", errorCampo["recargo"] ?: "Usa las tasas de la empresa.", borrador.re, errorCampo["recargo"] != null) {
                tocar(borrador.copy(re = it))
                errorCampo = errorCampo - "recargo"
            }
            Interruptor("Exento de IVA", null, borrador.exento) { tocar(borrador.copy(exento = it)) }
            Interruptor("IVA incluido en el precio", null, borrador.ivaIncluido) { tocar(borrador.copy(ivaIncluido = it)) }
            Spacer(Modifier.height(8.dp))
            Text("Líneas", style = MaterialTheme.typography.titleMedium)
            Text(
                "El IVA, el descuento y el recargo van de 0 a 100. El IVA admite los decimales que hagan falta; si lo deja vacío, el PC aplica 21.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            borrador.lineas.forEachIndexed { indice, linea ->
                LineaEditor(
                    linea = linea,
                    errores = errorLinea[indice].orEmpty(),
                    onCambio = { nueva ->
                        tocar(borrador.copy(lineas = borrador.lineas.map { if (it.clave == linea.clave) nueva else it }))
                        errorLinea = errorLinea - indice
                    },
                    onQuitar = {
                        val restantes = borrador.lineas.filter { it.clave != linea.clave }
                        tocar(borrador.copy(lineas = restantes.ifEmpty { listOf(LineaEditable(iva = ivaDefecto)) }))
                        errorLinea = emptyMap()
                    },
                )
            }
            TextButton(onClick = { tocar(borrador.copy(lineas = borrador.lineas + LineaEditable(iva = ivaDefecto))) }) {
                Icon(Icons.Filled.Add, null)
                Text("Añadir línea", modifier = Modifier.padding(start = 6.dp))
            }
            Text("El total lo calcula el PC al guardar.", modifier = Modifier.padding(top = 8.dp))
            if (error != null) Aviso(error!!)
            Spacer(Modifier.height(24.dp))
        }
    }

    if (fechaAbierta) {
        val estado = rememberDatePickerState(initialSelectedDateMillis = borrador.fecha.aMillis())
        DatePickerDialog(
            onDismissRequest = { fechaAbierta = false },
            confirmButton = {
                TextButton(onClick = {
                    estado.selectedDateMillis?.let { tocar(borrador.copy(fecha = it.aIso())) }
                    fechaAbierta = false
                }) { Text("Aceptar") }
            },
            dismissButton = { TextButton(onClick = { fechaAbierta = false }) { Text("Cancelar") } },
        ) { DatePicker(state = estado) }
    }
    if (confirmarSalida) {
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { confirmarSalida = false },
            title = { Text("Salir sin guardar") },
            text = { Text("Los cambios se pierden. En el móvil no queda copia.") },
            confirmButton = { TextButton(onClick = onAtras) { Text("Salir") } },
            dismissButton = { TextButton(onClick = { confirmarSalida = false }) { Text("Seguir") } },
        )
    }
}

@Composable
private fun LineaEditor(
    linea: LineaEditable,
    errores: Map<String, String>,
    onCambio: (LineaEditable) -> Unit,
    onQuitar: () -> Unit,
) {
    Card(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Column(Modifier.padding(12.dp)) {
            Interruptor("Línea de comentario", "Sin importe.", linea.comentario) { onCambio(linea.copy(comentario = it)) }
            Campo(linea.concepto, { onCambio(linea.copy(concepto = it)) }, "Concepto")
            if (!linea.comentario) {
                Campo(linea.cantidad, { onCambio(linea.copy(cantidad = it)) }, "Cantidad")
                Campo(linea.precio, { onCambio(linea.copy(precio = it)) }, "Precio", error = errores["precio"])
                Campo(linea.descuento, { onCambio(linea.copy(descuento = it)) }, "Descuento de la línea", error = errores["descuento"])
                Campo(linea.iva, { onCambio(linea.copy(iva = it)) }, "IVA", ayuda = "De 0 a 100. Vacío, el PC aplica 21.", error = errores["iva"])
            }
            TextButton(onClick = onQuitar) { Text("Quitar línea") }
        }
    }
}

@Composable
private fun Interruptor(titulo: String, ayuda: String?, valor: Boolean, fallo: Boolean = false, onCambio: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(titulo)
            if (ayuda != null) {
                Text(
                    ayuda,
                    color = if (fallo) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
        Switch(checked = valor, onCheckedChange = onCambio)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SelectorCliente(empresaId: Long, onCerrar: () -> Unit, onElegido: (soft.lomox.contfactu.nucleo.api.Cliente) -> Unit) {
    val app = LocalContext.current.applicationContext as ContFactuApp
    var q by remember { mutableStateOf("") }
    var cargando by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var clientes by remember { mutableStateOf<List<soft.lomox.contfactu.nucleo.api.Cliente>>(emptyList()) }
    LaunchedEffect(q) {
        delay(250)
        cargando = true
        try {
            clientes = app.repositorio.usar { it.clientes(empresaId, q = q.trim().ifBlank { null }, limite = 50) }.clientes
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
            title = { Text("Elegir cliente") },
            navigationIcon = { IconButton(onClick = onCerrar) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Volver") } },
        )
    }) { padding ->
        Columna(Modifier.padding(padding)) {
            Campo(q, { q = it }, "Buscar cliente")
            when {
                cargando && clientes.isEmpty() -> EstadoCarga("Consultando el PC…")
                error != null && clientes.isEmpty() -> EstadoError(error!!, onReintentar = { q = q })
                clientes.isEmpty() -> EstadoVacio("No hay clientes que coincidan.")
                else -> LazyColumn {
                    items(clientes, key = { it.id }) { cliente ->
                        Card(onClick = { onElegido(cliente) }, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                            Column(Modifier.padding(12.dp)) {
                                Text(cliente.nombreF ?: cliente.nombre.orEmpty(), fontWeight = FontWeight.Medium)
                                Text(listOfNotNull(cliente.nif, cliente.ciudad).joinToString(" · "), color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun PdfPantalla(empresaId: Long, facturaId: Long, onAtras: () -> Unit) {
    val app = LocalContext.current.applicationContext as ContFactuApp
    var paginas by remember { mutableStateOf<List<Bitmap>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var cargando by remember { mutableStateOf(true) }
    var intento by remember { mutableStateOf(0) }
    DisposableEffect(facturaId) { onDispose { app.cachePdf.borrar() } }
    LaunchedEffect(facturaId, intento) {
        try {
            val bytes = app.repositorio.usar { it.pdf(empresaId, facturaId) }
            val archivo = app.cachePdf.guardar(facturaId, bytes)
            paginas = withContext(Dispatchers.IO) { renderizar(archivo) }
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
            title = { Text("PDF") },
            navigationIcon = { IconButton(onClick = onAtras) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Volver") } },
        )
    }) { padding ->
        when {
            cargando -> EstadoCarga("Pidiendo el PDF al PC…")
            error != null -> EstadoError(error!!, onReintentar = { cargando = true; intento++ })
            else -> LazyColumn(Modifier.padding(padding).fillMaxSize()) {
                items(paginas.size) { i ->
                    Image(
                        paginas[i].asImageBitmap(),
                        contentDescription = "Página ${i + 1} de la factura",
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        contentScale = ContentScale.FillWidth,
                    )
                }
            }
        }
    }
}

private fun renderizar(archivo: File): List<Bitmap> {
    val fd = ParcelFileDescriptor.open(archivo, ParcelFileDescriptor.MODE_READ_ONLY)
    val renderer = PdfRenderer(fd)
    try {
        val total = renderer.pageCount.coerceAtMost(20)
        return (0 until total).map { indice ->
            renderer.openPage(indice).use { pagina ->
                val ancho = 1240
                val alto = (ancho.toFloat() * pagina.height / pagina.width).toInt().coerceAtLeast(1)
                Bitmap.createBitmap(ancho, alto, Bitmap.Config.ARGB_8888).also { bmp ->
                    bmp.eraseColor(android.graphics.Color.WHITE)
                    pagina.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                }
            }
        }
    } finally {
        renderer.close()
        fd.close()
    }
}

private class FacturasViewModel(private val app: ContFactuApp, private val empresaId: Long) : ViewModel() {
    var q by mutableStateOf("")
    var anioPedido by mutableStateOf<String?>(null)
    var anioVisible by mutableStateOf("")
    var anios by mutableStateOf<List<String>>(emptyList())
    var facturas by mutableStateOf<List<ResumenFactura>>(emptyList())
    var cargando by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    private var trabajo: Job? = null
    private var generacion = 0

    fun elegirAnio(anio: String) {
        anioPedido = anio
        anioVisible = anio
        cargar()
    }

    fun cargar() {
        val consulta = q
        val anio = anioPedido
        val gen = ++generacion
        trabajo?.cancel()
        cargando = true
        trabajo = viewModelScope.launch {
            delay(280)
            try {
                val r = app.repositorio.usar {
                    it.facturas(empresaId, anio = anio, q = consulta.trim().ifBlank { null })
                }
                if (gen != generacion) return@launch
                anios = r.anios
                if (anioPedido == null) anioVisible = r.anio
                facturas = r.facturas
                error = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (gen == generacion) error = textoError(e)
            } finally {
                if (gen == generacion) cargando = false
            }
        }
    }
}

private data class LineaEditable(
    val clave: Long = System.nanoTime(),
    val concepto: String = "",
    val cantidad: String = "1",
    val precio: String = "",
    val descuento: String = "0",
    val iva: String = "",
    val comentario: Boolean = false,
)

private data class Borrador(
    val fecha: String,
    val serie: String = "",
    val numero: String = "",
    val clienteId: Long? = null,
    val nombre: String = "",
    val direccion: String = "",
    val ciudad: String = "",
    val nif: String = "",
    val codigoCliente: String = "",
    val formaPago: String = "",
    val descuento: String = "0",
    val retencion: String = "0",
    val re: Boolean = false,
    val exento: Boolean = false,
    val ivaIncluido: Boolean = false,
    val lineas: List<LineaEditable> = listOf(LineaEditable()),
)

private fun Factura.aBorrador() = Borrador(
    fecha = fecha ?: hoyIso(),
    serie = serie,
    numero = numeroVisible,
    nombre = nombreF.orEmpty(),
    direccion = direccionF.orEmpty(),
    ciudad = ciudadF.orEmpty(),
    nif = nif.orEmpty(),
    codigoCliente = clienteCodigo.orEmpty(),
    formaPago = formaPago.orEmpty(),
    descuento = descuento,
    retencion = retencion,
    re = re,
    exento = exento,
    ivaIncluido = ivaIncluido,
    lineas = lineas.map {
        LineaEditable(
            concepto = it.concepto,
            cantidad = it.cantidad.ifBlank { "1" },
            precio = it.precio,
            descuento = it.descuento,
            iva = it.iva,
            comentario = it.comentario,
        )
    }.ifEmpty { listOf(LineaEditable()) },
)

private class DatosFormulario(
    val campos: Map<String, String>,
    val lineas: Map<Int, Map<String, String>>,
) : Exception("Revise los datos marcados.")

private fun Borrador.aEnvio(creando: Boolean): FacturaEnvio {
    val campos = mutableMapOf<String, String>()
    val porLinea = mutableMapOf<Int, MutableMap<String, String>>()
    fun enLinea(i: Int, campo: String, mensaje: String) {
        porLinea.getOrPut(i) { mutableMapOf() }[campo] = mensaje
    }
    if (!fecha.matches(Regex("""\d{4}-\d{2}-\d{2}"""))) campos["fecha"] = "La fecha tiene que ser AAAA-MM-DD."
    if (nombre.isBlank() && clienteId == null) campos["nombre"] = "Falta el nombre del cliente."
    if (lineas.isEmpty()) campos["nombre"] = campos["nombre"] ?: "Añada al menos una línea."
    val descuentoG = when (val r = Validacion.descuento(descuento)) {
        is ResultadoPorcentaje.Valido -> r.texto
        is ResultadoPorcentaje.Invalido -> {
            campos["descuento"] = r.mensaje
            "0"
        }
    }
    val enviadas = lineas.mapIndexed { i, linea ->
        if (linea.comentario) {
            LineaEnvio(concepto = linea.concepto.trim(), comentario = true)
        } else {
            val precio = try {
                Validacion.importe(linea.precio, "El precio")
            } catch (e: IllegalArgumentException) {
                enLinea(i, "precio", e.message ?: "El precio no es un número.")
                null
            }
            if (precio == null && !porLinea[i].orEmpty().containsKey("precio")) {
                enLinea(i, "precio", "Falta el precio de «${linea.concepto.ifBlank { "la línea" }}».")
            }
            val cantidad = try {
                Validacion.importe(linea.cantidad.ifBlank { "1" }, "La cantidad") ?: "1"
            } catch (e: IllegalArgumentException) {
                enLinea(i, "cantidad", e.message ?: "La cantidad no es un número.")
                "1"
            }
            val dto = when (val r = Validacion.descuento(linea.descuento)) {
                is ResultadoPorcentaje.Valido -> r.texto
                is ResultadoPorcentaje.Invalido -> {
                    enLinea(i, "descuento", r.mensaje)
                    "0"
                }
            }
            val iva = when (val r = Validacion.iva(linea.iva)) {
                ResultadoIva.Vacio -> null
                is ResultadoIva.Valido -> r.texto
                is ResultadoIva.Invalido -> {
                    enLinea(i, "iva", r.mensaje)
                    null
                }
            }
            LineaEnvio(
                concepto = linea.concepto.trim(),
                cantidad = cantidad,
                precio = precio,
                descuento = dto,
                iva = iva,
            )
        }
    }
    if (campos.isNotEmpty() || porLinea.isNotEmpty()) throw DatosFormulario(campos, porLinea)
    return FacturaEnvio(
        fecha = fecha,
        serie = if (creando) serie.trim().take(3).ifEmpty { null } else null,
        clienteId = clienteId,
        nombreF = nombre.trim().ifBlank { null },
        direccionF = direccion.trim().ifBlank { null },
        ciudadF = ciudad.trim().ifBlank { null },
        nif = nif.trim().ifBlank { null },
        clienteCodigo = codigoCliente.trim().ifBlank { null },
        formaPago = formaPago.trim().ifBlank { null },
        descuento = descuentoG,
        retencion = Validacion.importe(retencion.ifBlank { "0" }, "La retención") ?: "0",
        re = re,
        exento = exento,
        ivaIncluido = ivaIncluido,
        lineas = enviadas,
    )
}

private data class ErroresPuestos(
    val campos: Map<String, String>,
    val lineas: Map<Int, Map<String, String>>,
    val aviso: Boolean,
)

private fun colocarErrorServidor(e: PeticionRechazada): ErroresPuestos {
    val msg = e.message ?: "El PC ha rechazado el dato."
    val campo = e.campo ?: return ErroresPuestos(emptyMap(), emptyMap(), true)
    val indice = e.indice
    return when (campo) {
        "iva" -> if (indice != null) {
            ErroresPuestos(emptyMap(), mapOf(indice to mapOf("iva" to msg)), false)
        } else {
            ErroresPuestos(emptyMap(), emptyMap(), true)
        }
        "descuento" -> if (indice != null) {
            ErroresPuestos(emptyMap(), mapOf(indice to mapOf("descuento" to msg)), false)
        } else {
            ErroresPuestos(mapOf("descuento" to msg), emptyMap(), false)
        }
        "fecha" -> ErroresPuestos(mapOf("fecha" to msg), emptyMap(), false)
        "nif" -> ErroresPuestos(mapOf("nif" to msg), emptyMap(), false)
        "nombre", "nombre_f" -> ErroresPuestos(mapOf("nombre" to msg), emptyMap(), false)
        "direccion", "direccion_f" -> ErroresPuestos(mapOf("direccion" to msg), emptyMap(), false)
        "ciudad", "ciudad_f" -> ErroresPuestos(mapOf("ciudad" to msg), emptyMap(), false)
        "cp" -> ErroresPuestos(mapOf("cp" to msg), emptyMap(), false)
        "serie" -> ErroresPuestos(mapOf("serie" to msg), emptyMap(), false)
        "retencion" -> ErroresPuestos(mapOf("retencion" to msg), emptyMap(), false)
        "codigo", "cliente_codigo" -> ErroresPuestos(mapOf("codigo" to msg), emptyMap(), false)
        "recargo", "tipo_re", "re" -> ErroresPuestos(mapOf("recargo" to msg), emptyMap(), false)
        else -> ErroresPuestos(emptyMap(), emptyMap(), true)
    }
}

private fun String.aMillis(): Long? = try {
    LocalDate.parse(this).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
} catch (_: Exception) {
    null
}

private fun Long.aIso(): String = Instant.ofEpochMilli(this).atZone(ZoneOffset.UTC).toLocalDate().toString()

private fun colorEstado(estado: String?): Color = when (estado) {
    "cobrado" -> Color(0xFF2F6B4F)
    "parcial" -> Color(0xFF3D5A80)
    "pendiente" -> Color(0xFF8A5A12)
    else -> Color(0xFF5C6560)
}

private inline fun <reified T : ViewModel> fabrica(crossinline crear: () -> T) = object : ViewModelProvider.Factory {
    override fun <R : ViewModel> create(modelClass: Class<R>): R {
        @Suppress("UNCHECKED_CAST")
        return crear() as R
    }
}
