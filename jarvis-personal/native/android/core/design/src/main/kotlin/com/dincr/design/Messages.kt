package com.dincr.design

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.CloudOff
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material.icons.rounded.Verified
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.dincr.data.AppLanguage
import com.dincr.data.MessageKind
import com.dincr.design.generated.DincrRadius
import com.dincr.design.generated.DincrSpacing

/**
 * A message with its meaning (DESIGN.md → Messages): technical error, attention, opportunity or
 * positive. Each kind has its own icon, color and shape, and TalkBack reads the kind first.
 */
@Composable
fun DincrMessage(kind: MessageKind, title: String, message: String = "") {
    val style = messageStyle(kind)
    Row(
        Modifier.fillMaxWidth().height(IntrinsicSize.Min).clip(RoundedCornerShape(DincrRadius.md)).background(style.fill)
            .semantics(mergeDescendants = true) {},
    ) {
        // Attention carries a leading accent bar: it reads as "look here", never as a failure.
        if (kind == MessageKind.ATTENTION) Box(Modifier.width(4.dp).fillMaxHeight().background(style.color))
        Row(Modifier.padding(horizontal = DincrSpacing.s4, vertical = DincrSpacing.s3)) {
            // The icon carries the spoken kind, so TalkBack reads it before the title.
            Icon(style.icon, contentDescription = style.spokenKind, tint = style.color)
            Column(Modifier.padding(start = DincrSpacing.s3)) {
                Text(title, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                if (message.isNotBlank()) Text(message, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
            }
        }
    }
}

/**
 * Icon, colors and spoken name of each message kind. Technical errors are neutral (no financial
 * red or amber), so they can't be mistaken for a situation in the user's money.
 */
internal data class MessageStyle(val icon: ImageVector, val color: Color, val fill: Color, val spokenKind: String)

@Composable
internal fun messageStyle(kind: MessageKind): MessageStyle {
    val c = Dincr.colors
    val language = AppLanguage.current()
    return when (kind) {
        MessageKind.TECHNICAL_ERROR -> MessageStyle(Icons.Rounded.CloudOff, c.text2, c.surface2, language.pick("Problema técnico", "Technical problem"))
        MessageKind.ATTENTION -> MessageStyle(Icons.Rounded.NotificationsActive, c.warning, c.warningContainer, language.pick("Para atender", "Needs attention"))
        MessageKind.OPPORTUNITY -> MessageStyle(Icons.Rounded.AutoAwesome, c.info, c.infoContainer, language.pick("Recomendación", "Suggestion"))
        MessageKind.POSITIVE -> MessageStyle(Icons.Rounded.Verified, c.positive, c.positiveContainer, language.pick("Buenas noticias", "Good news"))
    }
}
