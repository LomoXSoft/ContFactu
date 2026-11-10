// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import soft.lomox.contfactu.ui.AppViewModel
import soft.lomox.contfactu.ui.EmparejarNav
import soft.lomox.contfactu.ui.EstadoApp
import soft.lomox.contfactu.ui.EstadoCarga
import soft.lomox.contfactu.ui.EstadoError
import soft.lomox.contfactu.ui.PrincipalNav
import soft.lomox.contfactu.ui.TemaContFactu

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TemaContFactu {
                Surface(Modifier.fillMaxSize()) {
                    val appVm: AppViewModel = viewModel()
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
                        when (val estado = appVm.estado) {
                            EstadoApp.Cargando -> EstadoCarga("Buscando el PC…")
                            EstadoApp.SinEmparejar -> EmparejarNav(onEmparejado = { appVm.refrescar() })
                            is EstadoApp.Listo -> PrincipalNav(appVm)
                            is EstadoApp.SinEnlace -> EstadoError(
                                estado.mensaje,
                                onReintentar = { appVm.refrescar() },
                                onOlvidar = { appVm.olvidar() },
                            )
                        }
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        if (isFinishing) {
            (application as ContFactuApp).cachePdf.borrar()
        }
        super.onDestroy()
    }
}
