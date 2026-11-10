// SPDX-License-Identifier: GPL-3.0-or-later

package soft.lomox.contfactu.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Tinta = Color(0xFF1B3A4B)
private val Papel = Color(0xFFF4F2EC)
private val Superficie = Color(0xFFFBF9F4)
private val Salvia = Color(0xFF3E5C52)
private val Error = Color(0xFF8E3B3B)
private val Noche = Color(0xFF12171B)
private val NocheSuperficie = Color(0xFF1C242B)

private val Claro = lightColorScheme(
    primary = Tinta,
    onPrimary = Color(0xFFF7F4EE),
    primaryContainer = Color(0xFFD5E2EA),
    onPrimaryContainer = Tinta,
    secondary = Salvia,
    onSecondary = Color(0xFFF7F4EE),
    background = Papel,
    onBackground = Color(0xFF1C2430),
    surface = Superficie,
    onSurface = Color(0xFF1C2430),
    surfaceVariant = Color(0xFFE7E2D8),
    onSurfaceVariant = Color(0xFF4A514C),
    outline = Color(0xFFD0CBC2),
    error = Error,
    onError = Color(0xFFFFF8F6),
)

private val Oscuro = darkColorScheme(
    primary = Color(0xFFD5E4EE),
    onPrimary = Color(0xFF0E2430),
    primaryContainer = Color(0xFF244556),
    onPrimaryContainer = Color(0xFFD5E4EE),
    secondary = Color(0xFFB7C9C0),
    onSecondary = Color(0xFF163028),
    background = Noche,
    onBackground = Color(0xFFE6E2DA),
    surface = NocheSuperficie,
    onSurface = Color(0xFFE6E2DA),
    surfaceVariant = Color(0xFF2A333B),
    onSurfaceVariant = Color(0xFFC5C0B6),
    outline = Color(0xFF3C464E),
    error = Color(0xFFF2B8B5),
    onError = Color(0xFF4A1515),
)

@Composable
fun TemaContFactu(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (isSystemInDarkTheme()) Oscuro else Claro,
        content = content,
    )
}
