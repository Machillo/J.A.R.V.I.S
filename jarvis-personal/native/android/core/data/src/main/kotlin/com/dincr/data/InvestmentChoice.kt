package com.dincr.data

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * A VIP chooses whether investing is in their plan (`GET/PUT /user-product/vip/investment-choice`):
 * off until they turn it on. iOS twin: `InvestmentChoice.swift`.
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class InvestmentChoice(@EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("wants_investing") val wantsInvesting: Boolean = false)
