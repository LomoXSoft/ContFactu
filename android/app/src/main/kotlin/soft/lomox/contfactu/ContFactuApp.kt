// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu

import android.app.Application
import soft.lomox.contfactu.datos.Repositorio
import soft.lomox.contfactu.pdf.CachePdf
import soft.lomox.contfactu.seguridad.AlmacenSeguro

class ContFactuApp : Application() {
    lateinit var repositorio: Repositorio
        private set
    lateinit var cachePdf: CachePdf
        private set

    override fun onCreate() {
        super.onCreate()
        cachePdf = CachePdf(this)
        repositorio = Repositorio(AlmacenSeguro(this))
        cachePdf.borrar()
    }
}
