package com.dincr.data

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Plan de dividendos (Owner; JARVIS → Patrimonio; `GET/PUT /finance/investment-center/dividend-plan`):
// how much capital a monthly dividend goal needs, with one or two stocks the Owner picks. Every
// figure is the backend's (`finance/dividend_plan.py`); one it did not send is unknown (null), never 0.
// iOS twin: `DividendPlan.swift`.

@Serializable
data class DividendPlan(
    val config: Config = Config(),
    @SerialName("held_symbols") val heldSymbols: List<String> = emptyList(),
    val gate: Gate = Gate(),
    val result: Result = Result(),
) {
    @OptIn(ExperimentalSerializationApi::class)
    @Serializable
    data class Stock(
        val symbol: String,
        @SerialName("share_pct") val sharePct: Money,
        @EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("yield_pct") val yieldPct: Money? = null,
    )

    @Serializable
    data class Config(
        val stocks: List<Stock> = emptyList(),
        @SerialName("goal_monthly_usd") val goalMonthlyUsd: Money? = null,
        @SerialName("monthly_amount_usd") val monthlyAmountUsd: Money? = null,
        @SerialName("withholding_pct") val withholdingPct: Money? = null,
    )

    @Serializable
    data class Gate(val open: Boolean = false, val blockers: List<Blocker> = emptyList()) {
        @Serializable data class Blocker(val code: String)
    }

    @Serializable
    data class Result(
        val ready: Boolean = false,
        @SerialName("net_yield_pct") val netYieldPct: Money? = null,
        @SerialName("capital_needed_usd") val capitalNeededUsd: Money? = null,
        @SerialName("current_value_usd") val currentValueUsd: Money? = null,
        @SerialName("missing_usd") val missingUsd: Money? = null,
        @SerialName("net_monthly_dividend_now_usd") val netMonthlyDividendNowUsd: Money? = null,
        @SerialName("months_to_goal") val monthsToGoal: Int? = null,
        @SerialName("monthly_needed") val monthlyNeeded: List<Horizon> = emptyList(),
        @SerialName("buy_this_month") val buyThisMonth: List<Purchase> = emptyList(),
    ) {
        @Serializable data class Horizon(val years: Int, @SerialName("amount_usd") val amountUsd: Money)
        @Serializable data class Purchase(val symbol: String, @SerialName("amount_usd") val amountUsd: Money)
    }

    /** No stock chosen yet: the card invites to set it up instead of showing empty figures. */
    val isConfigured: Boolean get() = config.stocks.isNotEmpty()
}

/** One number is enough: the monthly goal. The stocks and their yields come from what is held. */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class DividendGoalUpdate(
    @SerialName("goal_monthly_usd") val goalMonthlyUsd: Money,
    @EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("from_holdings") val fromHoldings: Boolean = true,
)

/** `POST /finance/investment-center/dividend-yield`: a stock's last year of dividends over its price. */
@Serializable
data class DividendYield(
    val symbol: String,
    @SerialName("yield_pct") val yieldPct: Money,
    @SerialName("annual_dividend_usd") val annualDividendUsd: Money? = null,
    @SerialName("price_usd") val priceUsd: Money? = null,
)

@Serializable
data class DividendYieldRequest(val symbol: String)

/** `PUT /finance/investment-center/dividend-plan`: every field is sent (a null clears it). */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class DividendPlanUpdate(
    val stocks: List<DividendPlan.Stock>,
    @EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("goal_monthly_usd") val goalMonthlyUsd: Money? = null,
    @EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("monthly_amount_usd") val monthlyAmountUsd: Money? = null,
    @EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("withholding_pct") val withholdingPct: Money? = null,
)
