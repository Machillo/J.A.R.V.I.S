import Foundation
import Testing
@testable import DincrCore

/// Owner information clarity: the Owner ledger's fields reach the app (backend owner_ledger), one
/// wording per concept is shared by the screens that show it, and nothing changes for other plans.
/// Android: OwnerReadingTest.kt.
struct OwnerReadingTests {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try APIClient.decoder.decode(type, from: Data(json.utf8))
    }

    @Test func theOwnerMonthCarriesTheLedgersReading() throws {
        let s = try decode(MonthlySummary.self, """
        {"period":"2026-10","income":450000.0,"expenses":125000.5,"gross_expenses":140000.5,"refunds":15000.0,
         "debt_paid":80000.0,"other_inflows":60000.0,"loan_received":50000.0,"receivable_payments":10000.0,
         "balance":244999.5,"cash_flow":304999.5,"unclassified_count":3,"pending_mail_count":2,
         "payroll_accrued":{"overtime_gross":42000.0,"vgh_gross":-5000.0,"bonuses_gross":0.0,"total_gross":37000.0},
         "complete":false,"incomplete_reasons":["pending_mail_review","unclassified_movements"]}
        """)
        #expect(s.isOwnerLedger)
        #expect(s.complete == false)
        #expect(s.incompleteReasons == ["pending_mail_review", "unclassified_movements"])
        #expect(s.refunds == 15000)
        #expect(s.loanReceived == 50000)
        #expect(s.payrollAccrued?.totalGross == 37000)
        #expect(s.payrollAccrued?.vghGross == -5000)
    }

    @Test func anotherPlansMonthIsNotTheOwnerLedger() throws {
        let s = try decode(MonthlySummary.self, #"{"period":"2026-10","income":100,"expenses":50,"debt_paid":0,"balance":50}"#)
        #expect(!s.isOwnerLedger)
        #expect(s.payrollAccrued == nil)
    }

    @Test func everyIncompleteReasonReadsInPlainWords() {
        #expect(OwnerReading.incompleteReason("pending_mail_review", pendingMail: 2, unclassified: nil, language: .spanish).contains("2 avisos de correo"))
        let unclassified = OwnerReading.incompleteReason("unclassified_movements", pendingMail: nil, unclassified: 3, language: .spanish)
        #expect(unclassified.contains("3 movimientos sin clasificar") && unclassified.contains("no suman"))
        #expect(OwnerReading.incompleteReason("payroll_without_deposit", pendingMail: nil, unclassified: nil, language: .spanish).contains("sin el depósito"))
        #expect(OwnerReading.incompleteReason("a_new_code", pendingMail: nil, unclassified: nil, language: .spanish).contains("Falta información"))
        #expect(OwnerReading.incompleteReason("pending_mail_review", pendingMail: nil, unclassified: nil, language: .english).hasPrefix("There are some"))
    }

    @Test func theIncompleteMonthsOfAFlowAreListed() throws {
        let flow = try decode([TransactionAnalysis.MonthPoint].self, """
        [{"month":"2026-08","complete":true},{"month":"2026-09","complete":false},
         {"month":"2026-10"},{"month":"2026-11","complete":false}]
        """)
        #expect(OwnerReading.incompleteMonths(flow) == ["2026-09", "2026-11"])
    }

    @Test func theOwnersFormulaIncomeIsWhatIsStillToCome() throws {
        let owner = try decode(DashboardStrategy.self, #"{"scope":"owner"}"#)
        let users = try decode(DashboardStrategy.self, #"{"scope":"users"}"#)
        #expect(OwnerReading.formulaLabel("income", plan: owner, language: .spanish) == "Ingresos por recibir en el ciclo")
        #expect(OwnerReading.formulaLabel("income", plan: users, language: .spanish) == DistributionLabels.formula("income", language: .spanish))
        #expect(OwnerReading.formulaLabel("surplus", plan: owner, language: .spanish) == DistributionLabels.formula("surplus", language: .spanish))
    }

    @Test func theOwnerStrategySaysWhichDatesItCovers() throws {
        let s = try decode(DashboardStrategy.self, """
        {"scope":"owner","cycle_period":{"start":"2026-10-06","end":"2026-11-05"},"card_statement_period":{"start":"2026-09-21","end":"2026-10-20"}}
        """)
        #expect(s.cyclePeriod == DatePeriod(start: "2026-10-06", end: "2026-11-05"))
        #expect(s.cardStatementPeriod == DatePeriod(start: "2026-09-21", end: "2026-10-20"))
        #expect(try decode(DashboardStrategy.self, #"{"scope":"users"}"#).cyclePeriod == nil)
    }
}
