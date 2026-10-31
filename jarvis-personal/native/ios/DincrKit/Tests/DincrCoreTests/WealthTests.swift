import Foundation
import Testing
@testable import DincrCore

/// WE-2 — Patrimonio: what you have and what you owe, as the backend counts it. An unknown part is
/// named and leaves net worth unknown (never 0). Android: `WealthTest.kt`. Synthetic data.
@Suite struct WealthTests {
    private func wealth(_ json: String) throws -> Wealth {
        try APIClient.decoder.decode(Wealth.self, from: Data(json.utf8))
    }

    private let complete = #"""
    {"assets":{"accounts":[{"name":"Cuenta","amount":100000,"currency":"CRC","original_amount":100000}],
               "salvavidas":{"name":"Salvavidas","amount":50000},"investments":[{"name":"Fondo","amount":75000}],"total":225000},
     "liabilities":{"debts":[{"name":"Préstamo","amount":200000},{"name":"Tarjeta","amount":100000}],"accounts":[{"name":"Sobregiro","amount":8000}],"total":308000},
     "net_worth":-83000,"complete":true,"unknown":[]}
    """#

    @Test func whatYouHaveIsAccountsThenTheSalvavidasThenInvestments() throws {
        let value = try wealth(complete)
        #expect(value.owned.map(\.name) == ["Cuenta", "Salvavidas", "Fondo"])
        #expect(value.netWorth == -83000 && value.missingNotice() == nil)
    }

    @Test func whatYouOweIsOneDebtLineAndEveryOverdraft() throws {
        let owed = try wealth(complete).owed(language: .spanish)
        #expect(owed.map(\.name) == ["Deudas", "Sobregiro"])
        #expect(owed.map(\.amount) == [300000, 8000])
    }

    @Test func anUnknownPartIsNamedAndTheTotalIsNotGuessed() throws {
        let value = try wealth(#"""
        {"assets":{"accounts":[],"salvavidas":{"name":"Salvavidas","amount":null},"investments":[],"total":0},
         "liabilities":{"debts":[{"name":"Préstamo","amount":null}],"accounts":[],"total":0},
         "net_worth":null,"complete":false,"unknown":["Salvavidas","Préstamo"]}
        """#)
        #expect(value.netWorth == nil)
        #expect(value.owed(language: .spanish).first?.amount == nil, "an unknown debt is not added as 0")
        #expect(value.missingNotice(language: .spanish) == "Falta el saldo de: Salvavidas, Préstamo. Cuando lo tengamos, te mostramos tu patrimonio neto.")
    }

    @Test func theFixtureAnswersVipAndTheOwnerAndRefusesTheRest() async throws {
        for role in [FixtureBackend.Role.user, .owner] {
            let value = try await FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, role: role, latency: .zero)).wealth()
            #expect(value.complete == true && value.netWorth != nil)
        }
        for plan in [PlanTier.free, .basic] {
            await #expect(throws: (any Error).self) {
                try await FixtureBackend.service(FixtureBackend(scenario: .populated, plan: plan, latency: .zero)).wealth()
            }
        }
    }
}
