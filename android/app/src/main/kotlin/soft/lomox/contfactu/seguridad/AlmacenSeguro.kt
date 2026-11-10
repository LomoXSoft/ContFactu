// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.seguridad

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import soft.lomox.contfactu.nucleo.api.ClienteApi
import soft.lomox.contfactu.nucleo.api.Sesion
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Token y huella cifrados con una clave AES del Android Keystore.
 * En las preferencias solo hay el criptograma. No se guarda ninguna factura ni cliente.
 */
class AlmacenSeguro(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun guardar(sesion: Sesion) {
        val claro = ClienteApi.sesionAJson(sesion).toByteArray(Charsets.UTF_8)
        val cifrado = cifrar(claro)
        prefs.edit().putString(CLAVE, Base64.encodeToString(cifrado, Base64.NO_WRAP)).apply()
    }

    fun leer(): Sesion? {
        val guardado = prefs.getString(CLAVE, null) ?: return null
        return try {
            val claro = descifrar(Base64.decode(guardado, Base64.NO_WRAP))
            ClienteApi.sesionDesdeJson(claro.toString(Charsets.UTF_8))
        } catch (_: Exception) {
            borrar()
            null
        }
    }

    fun borrar() {
        prefs.edit().clear().apply()
    }

    private fun clave(): SecretKey {
        val almacen = KeyStore.getInstance(ANDROID).apply { load(null) }
        (almacen.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generador = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID)
        val spec = KeyGenParameterSpec.Builder(
            ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .setRandomizedEncryptionRequired(true)
            .build()
        generador.init(spec)
        return generador.generateKey()
    }

    private fun cifrar(claro: ByteArray): ByteArray {
        val cipher = Cipher.getInstance(TRANSFORMACION)
        cipher.init(Cipher.ENCRYPT_MODE, clave())
        val iv = cipher.iv
        val datos = cipher.doFinal(claro)
        val salida = ByteArray(1 + iv.size + datos.size)
        salida[0] = iv.size.toByte()
        System.arraycopy(iv, 0, salida, 1, iv.size)
        System.arraycopy(datos, 0, salida, 1 + iv.size, datos.size)
        return salida
    }

    private fun descifrar(blob: ByteArray): ByteArray {
        if (blob.size < 14) error("blob corto")
        val largoIv = blob[0].toInt() and 0xff
        if (largoIv !in 12..32 || blob.size <= 1 + largoIv) error("iv")
        val iv = blob.copyOfRange(1, 1 + largoIv)
        val datos = blob.copyOfRange(1 + largoIv, blob.size)
        val cipher = Cipher.getInstance(TRANSFORMACION)
        cipher.init(Cipher.DECRYPT_MODE, clave(), GCMParameterSpec(128, iv))
        return cipher.doFinal(datos)
    }

    companion object {
        private const val PREFS = "contfactu_cifrado"
        private const val CLAVE = "sesion"
        private const val ALIAS = "contfactu_almacen_v1"
        private const val ANDROID = "AndroidKeyStore"
        private const val TRANSFORMACION = "AES/GCM/NoPadding"
    }
}
