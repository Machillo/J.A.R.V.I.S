package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonPrimitive

// JARVIS → Mi dinero (Owner): the current cycle (`GET /finance/cycle-report`: expected and received
// income, the statement period's spending, debt payments, goal reserves and the real balance) and the
// Owner's accounts (`GET /finance/account-balances`). Both reads never write; saving or removing an
// account is an explicit Owner command. Every amount is the backend's: one it did not send is
// unknown (null), never 0. iOS twin: `Money.swift`.

/** `GET /finance/cycle-report`. Only the figures the screen shows. */
@Serializable
data class CycleReport(
    val status: String? = null,
    @SerialName("as_of") val asOf: String? = null,
    /** The income cycle (5 → 5). */
    val cycle: Period? = null,
    /** The card statement period (21 → 21). */
    @SerialName("expense_cycle") val expenseCycle: Period? = null,
    val income: Income? = null,
    val expenses: Expenses? = null,
    val goals: Goals? = null,
    val cashflow: Cashflow? = null,
) {
    /** [closed]: the statement period only, whether it already closed. */
    @Serializable
    data class Period(val start: String? = null, val end: String? = null, val label: String? = null, val closed: Boolean? = null)

    @Serializable
    data class Income(
        @SerialName("fixed_expected") val fixedExpected: Money? = null,
        @SerialName("extra_expected") val extraExpected: Money? = null,
        @SerialName("expected_total") val expectedTotal: Money? = null,
        @SerialName("received_from_transactions") val receivedFromTransactions: Money? = null,
        /** The projected salary still to come (received salary replaces the projection). */
        @SerialName("pending_projection") val pendingProjection: Money? = null,
        @SerialName("other_cash_inflows") val otherCashInflows: Money? = null,
    )

    @Serializable
    data class Expenses(
        /** Spending plus debt payments. */
        @SerialName("current_period") val currentPeriod: Money? = null,
        @SerialName("spending_only") val spendingOnly: Money? = null,
        @SerialName("debt_payments") val debtPayments: Money? = null,
        @SerialName("transaction_count") val transactionCount: Int? = null,
    )

    @Serializable
    data class Goals(@SerialName("reserved_current_period") val reservedCurrentPeriod: Money? = null)

    @Serializable
    data class Cashflow(
        @SerialName("real_balance") val realBalance: Money? = null,
        @SerialName("loan_received") val loanReceived: Money? = null,
    )
}

/** `GET /finance/account-balances`: the Owner's active accounts and their real total in colones. */
@Serializable
data class AccountBalances(
    val items: List<Account> = emptyList(),
    /** The included accounts' total, in colones. */
    @SerialName("total_real_balance") val totalRealBalance: Money? = null,
    val currency: String? = null,
) {
    @Serializable
    data class Account(
        /** The backend's id: a number for a recorded account, a text (`ibkr-…`) for the brokerage snapshot. */
        @SerialName("id") val rawId: JsonPrimitive? = null,
        @SerialName("account_name") val accountName: String? = null,
        @SerialName("bank_name") val bankName: String? = null,
        @SerialName("account_last4") val accountLast4Wire: String? = null,
        val currency: String? = null,
        @SerialName("account_type") val accountType: String? = null,
        /** The last declared balance. */
        @SerialName("current_balance") val currentBalance: Money? = null,
        /** The declared balance plus the movements recorded since (absent for the brokerage snapshot). */
        @SerialName("calculated_balance") val calculatedBalance: Money? = null,
        @SerialName("balance_crc") val balanceCrc: Money? = null,
        @SerialName("balance_as_of") val balanceAsOf: String? = null,
        /** The backend's default: an account counts toward net worth unless it says otherwise. */
        @SerialName("include_in_net_worth") val includeInNetWorth: Boolean = true,
        @SerialName("read_only") val readOnly: Boolean = false,
        val source: String? = null,
        @SerialName("movements_since_balance") val movementsSinceBalance: Int? = null,
    ) {
        val id: String get() = rawId?.content.orEmpty()
        /** The numeric id a write needs; null for the brokerage snapshot. */
        val accountId: Long? get() = rawId?.content?.toLongOrNull()
        val accountLast4: String? get() = accountLast4Wire?.takeIf { it.isNotEmpty() }
        /** Only recorded accounts can be updated or removed here (the brokerage snapshot is read-only). */
        val isEditable: Boolean get() = !readOnly && accountId != null
        /** The balance shown: the calculated one when the backend sent it, else the declared one. */
        val balance: Money? get() = calculatedBalance ?: currentBalance
    }
}

/**
 * `POST /finance/account-balances`: creates or updates an account (identity: name + last 4 digits)
 * with the balance the Owner checked.
 */
@Serializable
data class AccountBalanceRequest(
    @SerialName("account_name") val accountName: String,
    @SerialName("current_balance") val currentBalance: Money,
    @SerialName("bank_name") val bankName: String = "",
    @SerialName("account_last4") val accountLast4: String = "",
    val currency: String = "CRC",
    @SerialName("account_type") val accountType: String = "checking",
    @SerialName("include_in_net_worth") val includeInNetWorth: Boolean = true,
    @SerialName("annual_interest_rate") val annualInterestRate: Money = java.math.BigDecimal.ZERO,
    val source: String = "manual",
    val note: String = "",
) {
    companion object {
        val currencies = listOf("CRC", "USD")
        val accountTypes = listOf("checking", "savings", "credit_card", "cash", "other")

        /** Empty, or exactly four digits. */
        fun isValidLast4(text: String): Boolean = text.isEmpty() || (text.length == 4 && text.all { it in '0'..'9' })
    }
}
