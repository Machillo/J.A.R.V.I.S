import Foundation
import Testing
@testable import DincrCore

/// JARVIS → Mi dinero (Owner): the cycle report and the accounts as the app reads them, and the
/// account request. Unknown amounts stay nil (never 0). Android: `MoneyTest`. Synthetic data only.
struct MoneyTests {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try APIClient.decoder.decode(type, from: Data(json.utf8))
    }

    @Test func theCycleReportReadsTheFiguresTheScreenShows() throws {
        let report = try decode(CycleReport.self, """
        {"status":"OK","as_of":"2026-10-25","cycle":{"start":"2026-10-05","end":"2026-11-04","label":"x","closing_day":5},
         "expense_cycle":{"start":"2026-09-21","end":"2026-10-20","closed":true},
         "income":{"fixed_expected":900000,"extra_expected":0,"expected_total":900000,"received_from_transactions":450000,
                   "pending_projection":450000,"other_cash_inflows":0,"items":[]},
         "expenses":{"current_period":380000,"spending_only":260000,"debt_payments":120000,"transaction_count":18,"items":[]},
         "goals":{"reserved_current_period":50000},"cashflow":{"real_balance":470000,"loan_received":0,"formula":"x"},"user_id":1}
        """)
        #expect(report.cycle?.start == "2026-10-05" && report.expenseCycle?.closed == true)
        #expect(report.income?.expectedTotal == 900_000 && report.income?.receivedFromTransactions == 450_000)
        #expect(report.income?.pendingProjection == 450_000)
        #expect(report.expenses?.spendingOnly == 260_000 && report.expenses?.debtPayments == 120_000 && report.expenses?.transactionCount == 18)
        #expect(report.goals?.reservedCurrentPeriod == 50_000)
        #expect(report.cashflow?.realBalance == 470_000)
    }

    @Test func aMissingFigureIsUnknownNotZero() throws {
        let report = try decode(CycleReport.self, #"{"status":"OK","income":{"expected_total":null},"expenses":{"spending_only":"n/a"}}"#)
        #expect(report.income?.expectedTotal == nil && report.income?.receivedFromTransactions == nil)
        #expect(report.expenses?.spendingOnly == nil && report.cashflow == nil && report.cycle == nil)
    }

    @Test func theAccountsReadEachBalanceAndWhichCanBeEdited() throws {
        let balances = try decode(AccountBalances.self, """
        {"status":"OK","total_real_balance":910000,"currency":"CRC","items":[
          {"id":901,"account_name":"Cuenta","bank_name":"Banco","account_last4":"1111","currency":"CRC","account_type":"checking",
           "current_balance":300000,"calculated_balance":310000,"balance_crc":310000,"balance_as_of":"2026-10-22T10:00:00",
           "include_in_net_worth":true,"source":"manual","movements_since_balance":2},
          {"id":903,"account_name":"Detectada","account_last4":"","current_balance":0,"include_in_net_worth":false},
          {"id":"ibkr-7","account_name":"Inversiones","currency":"USD","current_balance":1500,"read_only":true}]}
        """)
        #expect(balances.totalRealBalance == 910_000 && balances.items.map(\.id) == ["901", "903", "ibkr-7"])
        let first = balances.items[0]
        #expect(first.balance == 310_000 && first.accountLast4 == "1111" && first.accountId == 901 && first.isEditable)
        #expect(balances.items[1].accountLast4 == nil && !balances.items[1].includeInNetWorth && balances.items[1].balance == 0)
        #expect(balances.items[2].accountId == nil && !balances.items[2].isEditable && balances.items[2].balance == 1_500)
    }

    @Test func anAccountWithoutBalanceIsUnknownNotZero() throws {
        let balances = try decode(AccountBalances.self, #"{"status":"OK","items":[{"id":5,"account_name":"Sin saldo"}]}"#)
        #expect(balances.totalRealBalance == nil && balances.items[0].balance == nil)
    }

    @Test func theSaveSendsTheBackendsFieldNames() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let request = AccountBalanceRequest(accountName: "Cuenta", currentBalance: 50_000, bankName: "Banco", accountLast4: "4444", currency: "USD",
                                            accountType: "savings", includeInNetWorth: false)
        let body = String(decoding: try encoder.encode(request), as: UTF8.self)
        #expect(body == #"{"account_last4":"4444","account_name":"Cuenta","account_type":"savings","annual_interest_rate":0,"bank_name":"Banco","currency":"USD","current_balance":50000,"include_in_net_worth":false,"note":"","source":"manual"}"#)
    }

    @Test func theLastDigitsAreFourNumbersOrNothing() {
        #expect(AccountBalanceRequest.isValidLast4("") && AccountBalanceRequest.isValidLast4("0123"))
        #expect(!AccountBalanceRequest.isValidLast4("123") && !AccountBalanceRequest.isValidLast4("12a4") && !AccountBalanceRequest.isValidLast4("12345"))
    }

    @Test func moneyIsAnAvailableJarvisSection() {
        #expect(Jarvis.Section.money.isAvailable)
    }
}
