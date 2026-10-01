package com.dincr.app.ui

import androidx.annotation.DrawableRes
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccountBalance
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.dincr.app.R
import com.dincr.data.BankBranding
import com.dincr.design.Dincr
import com.dincr.design.generated.DincrRadius

/**
 * The historical institution assets (`frontend/src/assets/institutions/`, copied as-is; BAC as a
 * vector conversion of its SVG). Only these exist: no logo is downloaded or invented. An id without
 * an asset gets null and the caller shows the neutral fallback.
 */
@DrawableRes
fun bankLogoRes(id: String?): Int? = when (id) {
    "bac" -> R.drawable.bank_bac
    "bcr" -> R.drawable.bank_bcr
    "bn" -> R.drawable.bank_bn
    "davibank" -> R.drawable.bank_davibank
    "davivienda" -> R.drawable.bank_davivienda
    "multimoney" -> R.drawable.bank_multimoney
    "popular" -> R.drawable.bank_popular
    "promerica" -> R.drawable.bank_promerica
    else -> null
}

/**
 * A bank mark: the logo on a white tile (the assets are drawn for light backgrounds), or a neutral
 * fallback (initials, or a bank glyph when nothing is known). Decorative: the bank name is always
 * shown as text next to it.
 */
@Composable
fun BankLogo(bank: BankBranding.Bank?, modifier: Modifier = Modifier, size: Dp = 40.dp) {
    val logo = bank?.takeIf { it.hasLogo }?.let { bankLogoRes(it.id) }
    val shape = RoundedCornerShape(DincrRadius.md)
    if (logo != null) {
        // White logos (MultiMoney) sit on the historical dark tile; the rest on white.
        val tile = if (bank.logoNeedsDarkTile) Color(0xFF203046) else Color.White
        Box(modifier.size(size).background(tile, shape).border(1.dp, Dincr.colors.line, shape).padding(4.dp).testTag("bank.logo.${bank.id}"), contentAlignment = Alignment.Center) {
            Image(painterResource(logo), contentDescription = null, contentScale = ContentScale.Fit)
        }
    } else {
        Box(modifier.size(size).background(Dincr.colors.surface2, shape).testTag("bank.fallback"), contentAlignment = Alignment.Center) {
            val initials = bank?.short?.takeIf { it.isNotBlank() && it != "?" }
            if (initials != null) Text(initials, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2, maxLines = 1)
            else Icon(Icons.Rounded.AccountBalance, contentDescription = null, tint = Dincr.colors.textMuted)
        }
    }
}
