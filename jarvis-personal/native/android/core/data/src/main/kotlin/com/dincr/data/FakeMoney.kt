package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.serialization.json.JsonPrimitive

/**
 * The fake backend's JARVIS → Mi dinero (fixtures only). Same shapes as FastAPI's
 * `/finance/cycle-report` and `/finance/account-balances` (Owner routes; [FakeBackend] refuses
 * everyone else). Invented accounts and amounts. iOS: FixtureBackend+Money.swift.
 */
internal class FakeMoney(private val today: LocalDate, private val nextId: () -> Long) {
    private data class Account(
        val id: Long, val name: String, val bank: String, val last4: String, val currency: String, val type: String,
        val balance: BigDecimal, val includeInNetWorth: Boolean, val asOf: LocalDate,
    )

    private val accounts = mutableListOf(
        Account(901, "Cuenta de ejemplo", "Banco de ejemplo", "1111", "CRC", "checking", BigDecimal(310_000), true, today.minusDays(3)),
        Account(902, "Ahorro en dólares", "Banco de ejemplo", "2222", "USD", "savings", BigDecimal(1_200), true, today.minusDays(10)),
        Account(903, "Detectada por correo", "Banco de ejemplo", "3333", "CRC", "checking", BigDecimal.ZERO, false, today.minusDays(1)),
    )

    private fun crc(account: Account): BigDecimal = if (account.currency == "USD") account.balance * USD_RATE else account.balance

    private fun row(account: Account) = AccountBalances.Account(
        JsonPrimitive(account.id), account.name, account.bank, account.last4, account.currency, account.type, account.balance, account.balance,
        crc(account), account.asOf.toString(), account.includeInNetWorth, readOnly = false, source = "manual", movementsSinceBalance = 0,
    )

    fun cycleReport() = CycleReport(
        status = "OK", asOf = today.toString(),
        cycle = CycleReport.Period(today.minusDays(20).toString(), today.plusDays(10).toString()),
        expenseCycle = CycleReport.Period(today.minusDays(34).toString(), today.minusDays(4).toString(), closed = true),
        income = CycleReport.Income(BigDecimal(900_000), BigDecimal.ZERO, BigDecimal(900_000), BigDecimal(450_000), BigDecimal(450_000), BigDecimal.ZERO),
        expenses = CycleReport.Expenses(BigDecimal(380_000), BigDecimal(260_000), BigDecimal(120_000), 18),
        goals = CycleReport.Goals(BigDecimal(50_000)),
        cashflow = CycleReport.Cashflow(BigDecimal(470_000), BigDecimal.ZERO),
    )

    fun balances() = AccountBalances(
        accounts.map(::row),
        accounts.filter { it.includeInNetWorth }.fold(BigDecimal.ZERO) { sum, account -> sum + crc(account) },
        "CRC",
    )

    /** Creates or updates by name + last 4 digits, as the backend does. Null when the request is invalid (422). */
    fun save(name: String?, balance: BigDecimal?, bank: String?, last4: String?, currency: String?, type: String?, include: Boolean?): Acknowledgement? {
        val accountName = name?.trim().orEmpty()
        if (accountName.isEmpty() || balance == null) return null
        val digits = last4.orEmpty()
        val index = accounts.indexOfFirst { it.name.equals(accountName, ignoreCase = true) && it.last4 == digits }
        val account = Account(if (index >= 0) accounts[index].id else nextId(), accountName, bank.orEmpty(), digits, (currency ?: "CRC").uppercase(),
            type ?: "checking", balance, include ?: true, today)
        if (index >= 0) accounts[index] = account else accounts += account
        return Acknowledgement("OK")
    }

    /** Null when the account is unknown (the backend answers 404). */
    fun remove(id: Long?): Acknowledgement? = if (accounts.removeAll { it.id == id }) Acknowledgement("OK") else null

    private companion object {
        /** An invented colones-per-dollar rate for the fixture's totals. */
        val USD_RATE = BigDecimal(500)
    }
}
