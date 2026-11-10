// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import androidx.navigation.NavType
import soft.lomox.contfactu.ui.ajustes.AjustesPantalla
import soft.lomox.contfactu.ui.ajustes.LicenciaPantalla
import soft.lomox.contfactu.ui.buscar.BuscarPantalla
import soft.lomox.contfactu.ui.clientes.ClienteDetallePantalla
import soft.lomox.contfactu.ui.clientes.ClientesPantalla
import soft.lomox.contfactu.ui.emparejar.EmparejarPantalla
import soft.lomox.contfactu.ui.emparejar.EscanerPantalla
import soft.lomox.contfactu.ui.emparejar.ManualPantalla
import soft.lomox.contfactu.ui.facturas.DetalleFacturaPantalla
import soft.lomox.contfactu.ui.facturas.EditorFacturaPantalla
import soft.lomox.contfactu.ui.facturas.FacturasPantalla
import soft.lomox.contfactu.ui.facturas.PdfPantalla

private object Rutas {
    const val EMPAREJAR = "emparejar"
    const val ESCANER = "escaner"
    const val MANUAL = "manual"
    const val FACTURAS = "facturas"
    const val CLIENTES = "clientes"
    const val BUSCAR = "buscar"
    const val AJUSTES = "ajustes"
    const val LICENCIA = "licencia"
    const val NUEVA = "nueva"
    const val FACTURA = "factura/{id}"
    const val EDITAR = "editar/{id}"
    const val PDF = "pdf/{id}"
    const val CLIENTE = "cliente/{id}"
}

private data class Destino(val ruta: String, val etiqueta: String, val icono: ImageVector)

private val destinos = listOf(
    Destino(Rutas.FACTURAS, "Facturas", Icons.Filled.Description),
    Destino(Rutas.CLIENTES, "Clientes", Icons.Filled.People),
    Destino(Rutas.BUSCAR, "Buscar", Icons.Filled.Search),
    Destino(Rutas.AJUSTES, "Ajustes", Icons.Filled.Settings),
)

@Composable
fun EmparejarNav(onEmparejado: () -> Unit) {
    val nav = rememberNavController()
    val vm: EmparejarViewModel = viewModel()
    NavHost(nav, startDestination = Rutas.EMPAREJAR) {
        composable(Rutas.EMPAREJAR) {
            EmparejarPantalla(
                nombre = vm.nombre,
                onNombre = { vm.nombre = it },
                ocupado = vm.ocupado,
                error = vm.error,
                onEscanear = { nav.navigate(Rutas.ESCANER) },
                onManual = { nav.navigate(Rutas.MANUAL) },
            )
        }
        composable(Rutas.ESCANER) {
            EscanerPantalla(
                onTexto = { texto ->
                    try {
                        val qr = soft.lomox.contfactu.nucleo.qr.AnalizadorQr.analizar(texto)
                        vm.emparejar(qr, onEmparejado)
                        nav.popBackStack()
                    } catch (e: Exception) {
                        vm.error = textoError(e)
                        nav.popBackStack()
                    }
                },
                onAtras = { nav.popBackStack() },
                onManual = {
                    nav.navigate(Rutas.MANUAL) { popUpTo(Rutas.EMPAREJAR) }
                },
            )
        }
        composable(Rutas.MANUAL) {
            ManualPantalla(
                ocupado = vm.ocupado,
                error = vm.error,
                onAtras = { nav.popBackStack() },
                onDestino = { destino -> vm.emparejarManual(destino, onEmparejado) },
            )
        }
    }
}

@Composable
fun PrincipalNav(appVm: AppViewModel) {
    val nav = rememberNavController()
    val actual by nav.currentBackStackEntryAsState()
    val ruta = actual?.destination?.route
    val muestraBarra = ruta in destinos.map { it.ruta }
    Scaffold(
        bottomBar = {
            if (muestraBarra) {
                NavigationBar {
                    destinos.forEach { destino ->
                        NavigationBarItem(
                            selected = ruta == destino.ruta,
                            onClick = {
                                nav.navigate(destino.ruta) {
                                    popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(destino.icono, contentDescription = null) },
                            label = { Text(destino.etiqueta) },
                            alwaysShowLabel = true,
                        )
                    }
                }
            }
        },
    ) { padding ->
        NavHost(
            nav,
            startDestination = Rutas.FACTURAS,
            modifier = Modifier.padding(padding),
        ) {
            composable(Rutas.FACTURAS) {
                FacturasPantalla(
                    empresaId = appVm.empresaId,
                    empresas = appVm.empresas,
                    onEmpresa = { appVm.empresaId = it },
                    onAbrir = { nav.navigate("factura/$it") },
                    onNueva = { nav.navigate(Rutas.NUEVA) },
                )
            }
            composable(Rutas.NUEVA) {
                val id = appVm.empresaId
                if (id == null) {
                    EstadoVacio("El PC no tiene empresas.")
                } else {
                    EditorFacturaPantalla(
                        empresaId = id,
                        facturaId = null,
                        ivaDefecto = appVm.empresa?.ivas?.firstOrNull().orEmpty(),
                        onGuardada = { nueva ->
                            nav.popBackStack()
                            nav.navigate("factura/$nueva")
                        },
                        onAtras = { nav.popBackStack() },
                    )
                }
            }
            composable(Rutas.FACTURA, arguments = listOf(navArgument("id") { type = NavType.LongType })) { entry ->
                val idFactura = entry.arguments?.getLong("id") ?: return@composable
                val empresa = appVm.empresaId
                if (empresa == null) EstadoVacio("Elija una empresa.")
                else DetalleFacturaPantalla(
                    empresaId = empresa,
                    facturaId = idFactura,
                    onEditar = { nav.navigate("editar/$idFactura") },
                    onPdf = { nav.navigate("pdf/$idFactura") },
                    onAtras = { nav.popBackStack() },
                    onRevocado = { appVm.olvidar() },
                )
            }
            composable(Rutas.EDITAR, arguments = listOf(navArgument("id") { type = NavType.LongType })) { entry ->
                val idFactura = entry.arguments?.getLong("id") ?: return@composable
                val empresa = appVm.empresaId ?: return@composable
                EditorFacturaPantalla(
                    empresaId = empresa,
                    facturaId = idFactura,
                    ivaDefecto = appVm.empresa?.ivas?.firstOrNull().orEmpty(),
                    onGuardada = { nav.popBackStack() },
                    onAtras = { nav.popBackStack() },
                )
            }
            composable(Rutas.PDF, arguments = listOf(navArgument("id") { type = NavType.LongType })) { entry ->
                val idFactura = entry.arguments?.getLong("id") ?: return@composable
                val empresa = appVm.empresaId ?: return@composable
                PdfPantalla(empresa, idFactura) { nav.popBackStack() }
            }
            composable(Rutas.CLIENTES) {
                val empresa = appVm.empresaId
                if (empresa == null) EstadoVacio("El PC no tiene empresas.")
                else ClientesPantalla(empresa) { nav.navigate("cliente/$it") }
            }
            composable(Rutas.CLIENTE, arguments = listOf(navArgument("id") { type = NavType.LongType })) { entry ->
                val idCliente = entry.arguments?.getLong("id") ?: return@composable
                val empresa = appVm.empresaId ?: return@composable
                ClienteDetallePantalla(empresa, idCliente) { nav.popBackStack() }
            }
            composable(Rutas.BUSCAR) {
                val empresa = appVm.empresaId
                if (empresa == null) EstadoVacio("El PC no tiene empresas.")
                else BuscarPantalla(
                    empresaId = empresa,
                    onFactura = { nav.navigate("factura/$it") },
                    onCliente = { nav.navigate("cliente/$it") },
                )
            }
            composable(Rutas.AJUSTES) {
                AjustesPantalla(
                    sesion = (appVm.estado as? EstadoApp.Listo)?.sesion,
                    empresa = appVm.empresa?.nombre,
                    onOlvidar = { appVm.olvidar() },
                    onLicencia = { nav.navigate(Rutas.LICENCIA) },
                )
            }
            composable(Rutas.LICENCIA) { LicenciaPantalla { nav.popBackStack() } }
        }
    }
}
