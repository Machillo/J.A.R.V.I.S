package com.dincr.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The four message kinds (DESIGN.md → Messages): a financial alert is never shown as a technical
 * error, progress is never shown as a problem, and an unknown severity is never downplayed.
 * The Swift twin is `MessageKindTests`.
 */
class MessageKindTest {
    @Test fun everySeverityTheBackendSendsHasItsKind() {
        for (severity in listOf("critical", "high", "medium", "blocking", "warning")) {
            assertEquals(severity, MessageKind.ATTENTION, MessageKind.financial(severity))
        }
        assertEquals(MessageKind.POSITIVE, MessageKind.financial("success"))
        assertEquals(MessageKind.OPPORTUNITY, MessageKind.financial("low"))
        assertEquals(MessageKind.OPPORTUNITY, MessageKind.financial("info"))
    }

    @Test fun aFinancialAlertIsNeverATechnicalError() {
        for (severity in listOf("critical", "high", "medium", "low", "success", "blocking", "warning", "info", "error", "", "unexpected", null)) {
            assertNotEquals(severity.toString(), MessageKind.TECHNICAL_ERROR, MessageKind.financial(severity))
        }
    }

    @Test fun anUnknownOrMissingSeverityStaysVisibleAsAttention() {
        assertEquals(MessageKind.ATTENTION, MessageKind.financial(null))
        assertEquals(MessageKind.ATTENTION, MessageKind.financial(""))
        assertEquals(MessageKind.ATTENTION, MessageKind.financial("unexpected"))
        assertEquals(MessageKind.ATTENTION, MessageKind.financial("HIGH"))
        assertEquals(MessageKind.POSITIVE, MessageKind.financial("Success"))
    }

    /**
     * Screens never pick a look from a raw severity: every financial severity goes through
     * [MessageKind.financial], so the same alert looks the same everywhere.
     */
    @Test fun screensMapSeveritiesOnlyThroughMessageKind() {
        // Unit tests run in native/android/core/data: the screens are native/android/app/src/main.
        val android = File(System.getProperty("user.dir")).absoluteFile.parentFile.parentFile
        val files = File(android, "app/src/main").walkTopDown().filter { it.extension == "kt" }.toList()
        assertTrue(files.size > 20)
        val offenders = files.flatMap { file ->
            file.readLines().withIndex()
                .filter { (_, line) -> "severity" in line && "MessageKind.financial(" !in line }
                .map { (index, _) -> "${file.name}:${index + 1}" }
        }
        assertTrue("map severities with MessageKind.financial: $offenders", offenders.isEmpty())
    }
}
