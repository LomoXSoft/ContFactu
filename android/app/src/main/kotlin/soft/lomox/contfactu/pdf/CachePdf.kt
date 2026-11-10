// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.pdf

import android.content.Context
import java.io.File

/** PDF de factura en la caché temporal. Se borra al salir de la pantalla y al cerrar la aplicación. */
class CachePdf(context: Context) {
    private val dir = File(context.cacheDir, "pdfs").apply { mkdirs() }

    fun guardar(facturaId: Long, bytes: ByteArray): File {
        val archivo = File(dir, "factura-$facturaId.pdf")
        archivo.writeBytes(bytes)
        return archivo
    }

    fun borrar() {
        dir.listFiles()?.forEach { it.delete() }
    }
}
