package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// JARVIS → Patrimonio (Owner): the investment center (`GET /finance/investment-center`: the latest
// IBKR or manual portfolio snapshot, its positions and the money reserved to invest) and the
// business center (`GET /finance/business-center`: the Owner's businesses and their movements).
// Both reads never write. Refreshing from IBKR, creating a business and recording a movement are
// explicit Owner commands. Every amount is the backend's: one it did not send is unknown (null),
// never 0. iOS twin: `WealthCenter.swift`.

/** `GET /finance/investment-center`. */
@Serializable
data class InvestmentCenter(
    /** The latest portfolio snapshot. The backend sends `{}` when there is none. */
    val portfolio: Portfolio? = null,
    @SerialName("reserved_to_invest_crc") val reservedToInvestCrc: Money? = null,
    @SerialName("gross_pnl") val grossPnl: Money? = null,
    @SerialName("net_pnl") val netPnl: Money? = null,
    @SerialName("return_pct") val returnPct: Money? = null,
    val positions: List<Position> = emptyList(),
    @SerialName("sync_status") val syncStatus: String? = null,
    @SerialName("snapshot_age_seconds") val snapshotAgeSeconds: Long? = null,
    @SerialName("sync_method") val syncMethod: String? = null,
    /** Whether the server can refresh the snapshot from IBKR (Flex credentials configured). */
    @SerialName("flex_configured") val flexConfigured: Boolean = false,
    @SerialName("included_in_net_worth") val includedInNetWorth: Boolean? = null,
) {
    @Serializable
    data class Portfolio(
        @SerialName("market_value") val marketValue: Money? = null,
        @SerialName("contributed_capital") val contributedCapital: Money? = null,
        @SerialName("realized_pnl") val realizedPnl: Money? = null,
        @SerialName("unrealized_pnl") val unrealizedPnl: Money? = null,
        val dividends: Money? = null,
        val currency: String? = null,
        @SerialName("snapshot_at") val snapshotAt: String? = null,
        val source: String? = null,
    )

    /** One position of the snapshot (`investment_position_snapshots`). */
    @Serializable
    data class Position(
        val symbol: String? = null,
        @SerialName("sec_type") val secType: String? = null,
        val currency: String? = null,
        /** The quantity held. */
        @SerialName("position") val quantity: Money? = null,
        @SerialName("market_price") val marketPrice: Money? = null,
        @SerialName("market_value") val marketValue: Money? = null,
        @SerialName("unrealized_pnl") val unrealizedPnl: Money? = null,
    )

    /** The figures shown for the portfolio; only built when there is a snapshot. */
    data class Figures(val marketValue: Money, val contributedCapital: Money?, val netPnl: Money?, val returnPct: Money?, val currency: String?)

    enum class SyncState { CURRENT, STALE, MANUAL, UNKNOWN }

    /**
     * Whether there is a portfolio snapshot at all. Without one the backend still answers
     * `gross_pnl`, `net_pnl` and `return_pct` as 0: that is unknown, not a zero return.
     */
    val hasPortfolio: Boolean get() = portfolio?.marketValue != null

    /** The portfolio figures, or null when there is no snapshot (never ₡0 / 0 %). */
    val figures: Figures? get() {
        val snapshot = portfolio ?: return null
        val market = snapshot.marketValue ?: return null
        // No contributed capital: the backend's 0 % return is unknown, not a result.
        val hasCapital = (snapshot.contributedCapital?.signum() ?: 0) > 0
        return Figures(market, snapshot.contributedCapital, netPnl, if (hasCapital) returnPct else null, snapshot.currency)
    }

    val syncState: SyncState get() = when (syncStatus) {
        "current" -> SyncState.CURRENT
        "stale" -> SyncState.STALE
        "manual_ready_for_ibkr" -> SyncState.MANUAL
        else -> SyncState.UNKNOWN
    }

    /** Whole hours since the snapshot, or null when unknown. */
    val ageHours: Long? get() = snapshotAgeSeconds?.let { maxOf(0L, it) / 3600 }
}

/** `POST /finance/investment-center/sync-ibkr`: the server's answer after refreshing the snapshot. */
@Serializable
data class IbkrSyncResult(val status: String? = null, val positions: Int? = null)

/** `GET /finance/business-center`. */
@Serializable
data class BusinessCenter(
    val businesses: List<Business> = emptyList(),
    val movements: List<Movement> = emptyList(),
    val income: Money? = null,
    val expenses: Money? = null,
    val profit: Money? = null,
    val capital: Money? = null,
) {
    @Serializable
    data class Business(
        val id: Long,
        val name: String? = null,
        val description: String? = null,
        @SerialName("ownership_pct") val ownershipPct: Money? = null,
        val status: String? = null,
    )

    @Serializable
    data class Movement(
        val id: Long,
        @SerialName("business_id") val businessId: Long? = null,
        @SerialName("movement_date") val movementDate: String? = null,
        /** `income`, `expense` or `capital`. */
        @SerialName("movement_type") val movementType: String? = null,
        val amount: Money? = null,
        val description: String? = null,
        val category: String? = null,
    )

    /** The business's movements, newest first as the backend sent them, at most [limit]. */
    fun movementsOf(business: Business, limit: Int = 5): List<Movement> = movements.filter { it.businessId == business.id }.take(limit)
}

/** `POST /finance/business-center/businesses`. */
@Serializable
data class BusinessCreateRequest(
    val name: String,
    val description: String? = null,
    @SerialName("ownership_pct") val ownershipPct: Money = java.math.BigDecimal(100),
)

/**
 * `POST /finance/business-center/movements`. An income or expense also creates a transaction in the
 * Owner's ledger (backend `business_center.py`); capital does not.
 */
@Serializable
data class BusinessMovementRequest(
    @SerialName("business_id") val businessId: Long,
    @SerialName("movement_type") val movementType: String,
    val amount: Money,
    @SerialName("movement_date") val movementDate: String? = null,
    val description: String,
    val category: String? = null,
) {
    /** Whether the movement also lands in the Owner's transactions. */
    val createsTransaction: Boolean get() = movementType == "income" || movementType == "expense"

    companion object {
        val types = listOf("income", "expense", "capital")
    }
}

/** The answer of both business writes (the stored row). */
@Serializable
data class BusinessWriteResult(val id: Long? = null)
