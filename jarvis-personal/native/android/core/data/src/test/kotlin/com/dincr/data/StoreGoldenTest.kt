package com.dincr.data

import java.io.File
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

/**
 * `src/main/resources/store-sample.json` pins the STORE account in two halves:
 * - `inputs`: what the account holds (movements, debts, goals, recurring items, situation, budget
 *   limits, notices), written by this test from [StoreSample];
 * - `engine`: what the real backend computes from those inputs (strategy, VIP command center,
 *   guided budget), written by `backend/tests/test_store_sample_engine.py`, which runs the backend
 *   engines themselves. The fixture serves these responses as they are, so no screenshot shows advice
 *   the backend would not give.
 * Regenerate after changing StoreSample: `DINCR_UPDATE_STORE_GOLDEN=1 ./gradlew :core:data:test`, then
 * `DINCR_UPDATE_STORE_GOLDEN=1 python -m pytest backend/tests/test_store_sample_engine.py` (from jarvis-personal).
 */
class StoreGoldenTest {
    private val file = File("src/main/resources/store-sample.json")
    private val json = Json { prettyPrint = true; explicitNulls = false; encodeDefaults = false }

    private fun inputs(language: AppLanguage): JsonObject {
        val sample = StoreSample(language)
        return buildJsonObject {
            put("today", StoreSample.TODAY.toString())
            put("profile", json.encodeToJsonElement(sample.situation()))
            put("movements", json.encodeToJsonElement(sample.movements()))
            put("debts", json.encodeToJsonElement(sample.debts()))
            put("goals", json.encodeToJsonElement(sample.goals()))
            put("recurring", json.encodeToJsonElement(sample.recurring()))
            put("budget_items", json.encodeToJsonElement(sample.budget()))
            put("pending_notices", sample.candidates().count { it.isPending })
        }
    }

    @Test fun inputsMatchTheGoldenFile() {
        val stored = if (file.exists()) Json.parseToJsonElement(file.readText()).jsonObject else JsonObject(emptyMap())
        val languages = mapOf("es" to AppLanguage.SPANISH, "en" to AppLanguage.ENGLISH)
        if (System.getenv("DINCR_UPDATE_STORE_GOLDEN") == "1") {
            val updated = buildJsonObject {
                put("\$comment", "STORE sample for the store screenshots. inputs: StoreGoldenTest.kt (from StoreSample.kt). engine: backend/tests/test_store_sample_engine.py (real backend engines). Do not edit by hand.")
                for ((code, language) in languages) {
                    put(code, buildJsonObject {
                        put("inputs", inputs(language))
                        stored[code]?.jsonObject?.get("engine")?.let { put("engine", it) }
                    })
                }
            }
            file.parentFile.mkdirs()
            file.writeText(json.encodeToString(JsonObject.serializer(), updated) + "\n")
            return
        }
        for ((code, language) in languages) {
            val entry = stored[code]?.jsonObject
            assertNotNull("store-sample.json has no $code entry", entry)
            assertEquals("StoreSample changed: regenerate store-sample.json ($code)", inputs(language), entry!!["inputs"])
            assertNotNull("store-sample.json has no backend engine output for $code", entry["engine"])
        }
    }
}
