package com.dincr.data

/**
 * Cuentas (VIP + mail automation; the Owner by role): the second surface of the SAME review system
 * as Email Monitor. It groups what the backend already returns — the detected accounts
 * (`/vip/financial-identity`) and the review candidates (`/vip/gmail/emails`) — by bank. It never
 * shows or computes a balance (a detected account's stored balance is unknown, not zero) and never a
 * full account number; movements are the same candidates, with the same states and actions.
 */
object Accounts {
    /** The group of institutions DINCR does not identify ("Otras instituciones"). */
    const val OTHER = "other"

    data class BankGroup(
        /** A known bank id ([BankBranding.Bank.id]) or [OTHER]. */
        val key: String,
        /** The identified bank; null for [OTHER]. */
        val bank: BankBranding.Bank?,
        val accounts: List<FinancialIdentity.Account>,
        /**
         * The `bank=` filters of `/vip/gmail/emails`: the institution codes (the candidates' own `bank`
         * and the accounts' `institution_code`); `bank_name` is a display label only.
         */
        val bankQueries: List<String>,
        val movements: Int,
        val pending: Int,
    )

    private fun accountKey(account: FinancialIdentity.Account): String =
        (BankBranding.identify(account.institutionCode) ?: BankBranding.identify(account.bankName))?.id ?: OTHER

    /**
     * Groups by bank, known banks in their historical order and then [OTHER]. A candidate belongs to
     * its bank (its `bank` is the institution code), or to the bank of the detected account it is
     * linked to; a detected account by its `institution_code` (its `bank_name` is only a label). A
     * known bank without a detected account still gets its group; a candidate with no bank and no
     * account is only in Email Monitor.
     */
    fun group(accounts: List<FinancialIdentity.Account>, candidates: List<MailCandidate>): List<BankGroup> {
        val byAccount = accounts.associateBy { it.id }
        fun candidateKey(c: MailCandidate): String? =
            BankBranding.identify(c.bank)?.id
                ?: c.financialAccountId?.let { byAccount[it] }?.let(::accountKey)
                ?: c.bank?.takeIf { it.isNotBlank() }?.let { OTHER }
        val accountGroups = accounts.groupBy(::accountKey)
        val candidateGroups = candidates.mapNotNull { c -> candidateKey(c)?.let { it to c } }.groupBy({ it.first }, { it.second })
        val order = BankBranding.KNOWN.map { it.id } + OTHER
        return order.filter { it in accountGroups || it in candidateGroups }.map { key ->
            val rows = candidateGroups[key].orEmpty()
            BankGroup(
                key = key,
                bank = BankBranding.KNOWN.firstOrNull { it.id == key },
                accounts = accountGroups[key].orEmpty(),
                bankQueries = (rows.map { it.bank } + accountGroups[key].orEmpty().map { it.institutionCode })
                    .mapNotNull { it?.trim()?.takeIf(String::isNotEmpty) }.distinctBy { it.lowercase() },
                movements = rows.size,
                pending = rows.count { it.isPending },
            )
        }
    }

    /** "•••• 1234": never more than the last four digits the backend stores. */
    fun maskedLabel(account: FinancialIdentity.Account): String? =
        account.accountLast4?.filter(Char::isDigit)?.takeLast(4)?.takeIf { it.isNotEmpty() }?.let { "•••• $it" }

    /** Candidates of several `bank=` queries, merged once each, newest first. */
    fun merge(lists: List<List<MailCandidate>>): List<MailCandidate> =
        lists.flatten().distinctBy { it.candidateId ?: it.emailId }.sortedByDescending { it.receivedAt ?: it.transactionDate }
}
