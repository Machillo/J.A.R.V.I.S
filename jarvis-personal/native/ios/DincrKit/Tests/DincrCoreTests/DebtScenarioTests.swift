import Foundation
import Testing
@testable import DincrCore

/// Debt what-ifs (VIP): the request the backend expects, unknown values kept unknown, and the
/// fixture's VIP gate and errors (Android: `DebtScenarioTest`).
@Suite struct DebtScenarioTests {
    @Test func requestsAreSnakeCaseWithoutEmptyFields() throws {
        let payOff = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(DebtScenarioRequest.payOff(debtId: 7))) as? [String: Any]
        #expect(payOff?["kind"] as? String == "pay_off")
        #expect(payOff?["debt_id"] as? Int == 7)
        #expect(payOff?.keys.sorted() == ["debt_id", "kind"])
        let newDebt = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(
            DebtScenarioRequest.newDebt(name: "Moto", amount: 1_200_000, monthlyPayment: nil, annualRate: 24, termMonths: 24))) as? [String: Any]
        #expect(newDebt?.keys.sorted() == ["amount", "annual_rate", "kind", "name", "term_months"])
    }

    @Test func unknownFiguresDecodeAsNilNeverZero() throws {
        let json = """
        {"rule_version":"debt-scenarios-v1","kind":"extra_payment",
         "debt":{"id":2,"name":"Préstamo","remaining_amount":2400000,"monthly_payment":100000,"interest_rate":null,"debt_type":"loan"},
         "monthly_leftover":{"current":null,"scenario":null,"change":null},"one_time_amount":600000,"liquid_savings_after":null,
         "options":{"lower_installment":{"monthly_payment":null,"monthly_leftover":null,"change":null},
                    "shorter_term":{"monthly_payment":100000,"monthly_leftover":null,"months_saved":null,"interest_saved":null}},
         "payoff":null,"warnings":["Esta deuda no tiene tasa de interés conocida."],"explanation":"Tu banco decide."}
        """
        let result = try APIClient.decoder.decode(DebtScenarioResult.self, from: Data(json.utf8))
        #expect(result.monthlyLeftover.current == nil && result.monthlyLeftover.change == nil)
        #expect(result.options?.lowerInstallment?.monthlyPayment == nil)
        #expect(result.options?.shorterTerm?.monthlyPayment == 100_000)
        #expect(result.liquidSavingsAfter == nil && result.oneTimeAmount == 600_000)
        #expect(result.debt?.interestRate == nil)
    }

    @Test func theFixtureAnswersEachScenarioForVip() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let debt = try #require(try await service.debts().first { ($0.monthlyPayment ?? 0) > 0 && ($0.remainingAmount ?? 0) > 0 })
        let payOff = try await service.debtScenario(.payOff(debtId: debt.id))
        #expect(payOff.monthlyLeftover.change == debt.monthlyPayment)
        #expect(payOff.oneTimeAmount == debt.remainingAmount)
        let extra = try await service.debtScenario(.extraPayment(debtId: debt.id, amount: 10_000))
        #expect(extra.options?.shorterTerm?.monthlyPayment == debt.monthlyPayment)
        #expect((extra.options?.lowerInstallment?.monthlyPayment ?? 0) < (debt.monthlyPayment ?? 0))
        let newDebt = try await service.debtScenario(.newDebt(name: nil, amount: 120_000, monthlyPayment: 10_000, annualRate: nil, termMonths: nil))
        #expect(newDebt.monthlyLeftover.change == -10_000)
    }

    @Test func theFixtureRefusesWhatTheBackendRefuses() async throws {
        let free = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .free, latency: .zero))
        await #expect(throws: APIError.self) { _ = try await free.debtScenario(.payOff(debtId: 1)) }
        let vip = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let debt = try #require(try await vip.debts().first { ($0.remainingAmount ?? 0) > 0 })
        do {
            _ = try await vip.debtScenario(.extraPayment(debtId: debt.id, amount: debt.remainingAmount ?? 0))
            Issue.record("an extra payment covering the debt must be refused")
        } catch let error as APIError {
            #expect(error.status == 422)
        }
        do {
            _ = try await vip.debtScenario(.payOff(debtId: 999_999))
            Issue.record("an unknown debt must be refused")
        } catch let error as APIError {
            #expect(error.status == 404)
        }
    }
}
