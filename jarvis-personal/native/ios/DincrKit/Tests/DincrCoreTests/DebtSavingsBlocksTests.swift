import Foundation
import Testing
@testable import DincrCore

/// DB-1 — Plan → Ahorro para deudas (Owner): the backend's proposal decoded and said in short
/// sentences, and the reminder on the day a block matures. Android: `DebtSavingsBlocksTest.kt`.
/// Synthetic data.
@Suite struct DebtSavingsBlocksTests {
    private let colones = MoneyFormat(currency: "CRC", separators: .dotComma)
    private let calendar = Calendar(identifier: .gregorian)

    static let proposalJSON = """
    {"status": "proposal", "weekly_safe_amount": 13500.0, "committed_weekly": 0.0, "savings_interest_counted": false,
     "warnings": ["average_income_estimated", "something_new"], "short_debts": [],
     "proposal": {"mode": "block", "debt": {"id": 801, "name": "Préstamo de ejemplo", "remaining_amount": 1200000.0, "interest_rate": 24.0},
                  "weekly_amount": 13500.0, "contributions": 26, "term_months": 6, "start_date": "2026-11-05", "maturity_date": "2027-05-05",
                  "total_saved": 351000.0, "abono_amount": 351000.0, "balance_at_maturity": 1020000.0, "balance_after_abono": 669000.0,
                  "lock_cost": 21400.0, "recommendation": {"choice": "reduce_term", "reason": "saves_interest"}},
     "blocks": [{"id": "b1", "debt_id": 802, "debt_name": "Tarjeta de ejemplo", "mode": "block", "weekly_amount": 5000.0,
                 "start_date": "2026-10-01", "maturity_date": "2027-01-01", "term_months": 3, "contributions_total": 14,
                 "contributions_done": 5, "saved_so_far": 25000.0, "total_at_maturity": 70000.0, "next_date": "2026-11-05", "matured": false}]}
    """

    private func state(_ json: String = Self.proposalJSON) throws -> DebtSavingsBlocks {
        try APIClient.decoder.decode(DebtSavingsBlocks.self, from: Data(json.utf8))
    }

    @Test func theProposalIsSaidInShortSentences() throws {
        let state = try state()
        let proposal = try #require(state.proposal)
        #expect(DebtSavingsReading.headline(proposal, format: colones, language: .spanish) == "Ahorrá ₡13.500 cada jueves por 6 meses")
        #expect(DebtSavingsReading.lines(state, format: colones, language: .spanish) == [
            "Es para Préstamo de ejemplo, la deuda que sigue en tu estrategia.",
            "Empieza el 5 nov 2026 y vence el 5 may 2027.",
            "Ese día le abonás ₡351.000 a Préstamo de ejemplo y te queda debiendo unos ₡669.000.",
            "Bloquearlo te cuesta unos ₡21.400 en intereses frente a abonar cada semana. Es el precio de no ver esa plata.",
            "Los intereses del ahorro no se cuentan: si llegan, son ganancia.",
        ])
        #expect(DebtSavingsReading.recommendation(proposal, language: .spanish).hasPrefix("Al abonar, pedile al banco bajar el plazo: así ahorrás más intereses."))
        #expect(DebtSavingsReading.statusMessage(state) == nil)
    }

    @Test func onlyKnownWarningsAreShown() throws {
        #expect(DebtSavingsReading.warnings(try state(), language: .spanish) == ["Algunos salarios de los últimos 3 meses son estimados."])
    }

    @Test func preSavingNamesTheShortDebtsPaidFirst() throws {
        let json = Self.proposalJSON
            .replacingOccurrences(of: "\"mode\": \"block\", \"debt\"", with: "\"mode\": \"presave\", \"debt\"")
            .replacingOccurrences(of: "\"short_debts\": []", with: "\"short_debts\": [{\"id\": 9, \"name\": \"Tienda de ejemplo\", \"payoff_month\": 2}]")
        #expect(DebtSavingsReading.lines(try state(json), format: colones, language: .spanish).first
                == "Mientras terminás de pagar Tienda de ejemplo, vas guardando para Préstamo de ejemplo.")
    }

    @Test func withoutAProposalItSaysWhy() throws {
        let none = { (status: String, committed: Int) in
            try self.state("{\"status\": \"\(status)\", \"weekly_safe_amount\": 0, \"committed_weekly\": \(committed), \"proposal\": null}")
        }
        #expect(DebtSavingsReading.statusMessage(try none("short_debts_only", 0), language: .spanish)
                == "Tus deudas se terminan en 3 meses o menos: seguí pagándolas directo.")
        #expect(DebtSavingsReading.statusMessage(try none("no_surplus", 13500), language: .spanish)
                == "Tus ahorros bloqueados ya usan todo tu sobrante seguro de cada jueves.")
        #expect(DebtSavingsReading.statusMessage(try none("no_surplus", 0), language: .spanish)
                == "Con tu salario sin extras no queda plata segura para bloquear.")
        #expect(DebtSavingsReading.lines(try none("no_debts", 0), format: colones).isEmpty)
    }

    @Test func aBlockShowsItsProgressOrWhatToDoWhenItMatured() throws {
        let block = try #require(try state().blocks?.first)
        #expect(DebtSavingsReading.blockLines(block, format: colones, language: .spanish) == [
            "₡5.000 cada jueves", "Llevás ₡25.000 de ₡70.000 (5 de 14 jueves).", "Vence el 1 ene 2027."])
        let matured = try APIClient.decoder.decode(DebtSavingsBlocks.Block.self, from: Data("""
            {"id": "b2", "debt_name": "Tarjeta de ejemplo", "maturity_date": "2027-01-01", "total_at_maturity": 70000, "matured": true}
            """.utf8))
        #expect(DebtSavingsReading.blockLines(matured, format: colones, language: .spanish) == ["Venció el 1 ene 2027: abonale ₡70.000 a Tarjeta de ejemplo."])
    }

    @Test func theDayABlockMaturesThePhoneSaysWhatToPay() throws {
        let blocks = try state().blocks ?? []
        let today = calendar.date(from: DateComponents(year: 2026, month: 12, day: 20))!
        let plan = Reminders.plan(today: today, bills: [], saving: nil, blocks: blocks, days: 20, format: colones, language: .spanish)
        let reminder = try #require(plan.first { $0.id.hasPrefix("dincr.reminder.block.b1") })
        #expect((reminder.date.year, reminder.date.month, reminder.date.day) == (2027, 1, 1))
        #expect(reminder.title == "Hoy vence tu ahorro bloqueado" && reminder.body == "Abonale ₡70.000 a Tarjeta de ejemplo.")
        let before = calendar.date(from: DateComponents(year: 2026, month: 11, day: 1))!
        #expect(!Reminders.plan(today: before, bills: [], saving: nil, blocks: blocks, days: 35, format: colones).contains { $0.id.contains(".block.") })
    }

    @Test func afterTheAbonoItSaysWhereTheDebtStandsAndWhatWasLeft() throws {
        let decode = { (json: String) in try APIClient.decoder.decode(DebtSavingsBlockApplied.self, from: Data(json.utf8)).block.applied }
        #expect(DebtSavingsReading.appliedMessage(try decode(#"{"block": {"id": "b1", "applied": {"amount": 351000, "outcome": "reduce_term", "new_remaining_amount": 649000, "left_over": 0}}}"#),
                                                  format: colones, language: .spanish) == "Listo: tu deuda quedó en ₡649.000.")
        #expect(DebtSavingsReading.appliedMessage(try decode(#"{"block": {"id": "b1", "applied": {"amount": 1050000, "outcome": "reduce_term", "new_remaining_amount": 0, "left_over": 50000}}}"#),
                                                  format: colones, language: .spanish)
                == "Listo: terminaste de pagar esa deuda. Te sobraron ₡50.000: mandalos a tu siguiente deuda o al Salvavidas.")
    }

    @Test func theAbonoCarriesTheNewInstallmentOnlyWhenTheBankLoweredIt() throws {
        let term = try String(decoding: APIClient.encoder.encode(DebtSavingsBlockApply(amount: 351000, outcome: .reduceTerm, newMonthlyPayment: 39000)), as: UTF8.self)
        #expect(term.contains("\"outcome\":\"reduce_term\"") && !term.contains("39000"))
        let lower = try String(decoding: APIClient.encoder.encode(DebtSavingsBlockApply(amount: 351000, outcome: .reduceInstallment, newMonthlyPayment: 39000)), as: UTF8.self)
        #expect(lower.contains("\"new_monthly_payment\":39000"))
    }

    @Test func aShorterTermCarriesTheInstallmentsLeft() throws {
        let body = try String(decoding: APIClient.encoder.encode(DebtSavingsBlockApply(amount: 351000, outcome: .reduceTerm, newMonthlyPayment: nil,
                                                                                         remainingInstallments: 12)), as: UTF8.self)
        #expect(body.contains("\"remaining_installments\":12"))
    }

    @Test func aDebtPaymentCarriesWhatTheBankDidOnlyWhenTheUserSaidIt() throws {
        func body(_ after: DebtAfterExtra?) throws -> String {
            try String(decoding: APIClient.encoder.encode(DebtPaymentRequest(amount: 141500, afterExtra: after)), as: UTF8.self)
        }
        #expect(try body(nil) == "{\"amount\":141500}")
        #expect(try body(.remainingInstallments(10)).contains("\"remaining_installments\":10"))
        let lower = try body(.newMonthlyPayment(4104))
        #expect(lower.contains("\"new_monthly_payment\":4104") && !lower.contains("remaining"))
    }
}
