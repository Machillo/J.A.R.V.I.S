package com.dincr.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.generated.DincrColorStyles
import com.dincr.design.generated.DincrSpacing

/** Perfil → Estilo de colores: every plan picks one, it applies at once and stays on this device. iOS: `ColorStyleView`. */
@Composable
fun ColorStyleScreen(model: AppModel, nav: Navigator) {
    val current by model.appearance.colorStyle.collectAsStateWithLifecycle()
    DetailScaffold(tx("Estilo de colores", "Color style"), nav::back) {
        DincrColorStyles.all.forEach { style ->
            val selected = current == style.id
            DincrCard(Modifier.testTag("colorStyle.${style.id}").selectable(selected, role = Role.RadioButton) { model.appearance.selectColorStyle(style.id) }) {
                Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(tx(style.nameEs, style.nameEn), Modifier.weight(1f), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                        RadioButton(selected, null)
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                        style.swatches.forEach { color -> Box(Modifier.weight(1f).height(28.dp).background(color, CircleShape)) }
                    }
                }
            }
        }
        Caption(tx("Se guarda en este teléfono. Las alertas siguen usando verde, rojo y ámbar.", "It stays on this phone. Alerts keep using green, red and amber."))
    }
}
