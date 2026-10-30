import Foundation
import Testing
@testable import DincrCore

/// Salvavidas automatic contributions (VIP and the Owner) and the Owner's interest rate: decoding
/// `auto_contribution` / `declared_amount` / `annual_interest_rate`, the PUT body, the client-side
/// checks and the fixture's contract (backend: finance/salvavidas_plan.py). Synthetic figures only.
/// Android: `SalvavidasPlanTest.kt`.
@Suite struct SalvavidasPlanTests {
    static func decode(_ json: String) throws -> Salvavidas {
        try APIClient.decoder.decode(Salvavidas.self, from: Data(json.utf8))
    }

    static func body(_ update: SalvavidasUpdate?) throws -> String {
        String(decoding: try APIClient.encoder.encode(try #require(update)), as: UTF8.self)
    }

    static func service(_ transport: ScriptedTransport) -> DincrService {
        DincrService(client: APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(), transport: transport, language: .spanish, backoff: { _ in }))
    }

    @Test func anEnabledPlanDecodesWithItsBreakdown() throws {
        let fund = try Self.decode(#"""
        {"status":"OK","scope":"users","current_amount":130000,"current_amount_known":true,"declared_amount":100000,
         "auto_contribution":{"enabled":true,"amount":10000,"frequency":"weekly","start_date":"2026-10-01","end_date":null,
          "base_amount":100000,"base_date":"2026-09-30","contributions_count":3,"contributions_amount":30000,
          "estimated_interest":0,"next_date":"2026-10-22","total":130000}}
        """#)
        let plan = try #require(fund.activePlan)
        #expect(fund.declaredAmount == 100_000 && fund.currentAmount == 130_000)
        #expect(plan.amount == 10_000 && plan.frequency == "weekly" && plan.startDate == "2026-10-01" && plan.endDate == nil)
        #expect(plan.contributionsCount == 3 && plan.contributionsAmount == 30_000 && plan.total == 130_000)
        #expect(plan.nextDate == "2026-10-22" && plan.baseDate == "2026-09-30")
        #expect(!fund.offersInterestRate && fund.annualInterestRate == nil, "Users never get the interest rate")
        #expect(SalvavidasAutoContribution.countLabel(3, language: .spanish) == "3 aportes automáticos")
        #expect(SalvavidasAutoContribution.countLabel(1, language: .english) == "1 automatic contribution")
        #expect(SalvavidasAutoContribution.frequencyLabel("biweekly", language: .spanish) == "Quincenal")
    }

    @Test func noPlanADisabledPlanAndUnknownSavings() throws {
        let none = try Self.decode(#"{"scope":"users","current_amount":null,"current_amount_known":false,"declared_amount":null,"auto_contribution":null}"#)
        #expect(none.autoContribution == nil && none.activePlan == nil && none.declaredAmount == nil && !none.savingsKnown)
        // A disabled plan keeps its settings to edit, but nothing is added to the balance.
        let disabled = try Self.decode(#"""
        {"scope":"users","current_amount":50000,"current_amount_known":true,"declared_amount":50000,
         "auto_contribution":{"enabled":false,"amount":5000,"frequency":"monthly","start_date":"2026-11-15","end_date":"2027-06-15",
          "contributions_count":0,"contributions_amount":0,"estimated_interest":0,"next_date":null,"total":50000}}
        """#)
        #expect(disabled.autoContribution?.isEnabled == false && disabled.activePlan == nil)
        #expect(disabled.autoContribution?.endDate == "2027-06-15" && disabled.autoContribution?.nextDate == nil)
        // Missing fields (an older backend) decode as nil, never as zero.
        let old = try Self.decode(#"{"scope":"users","current_amount":1000,"current_amount_known":true}"#)
        #expect(old.autoContribution == nil && old.declaredAmount == nil)
    }

    @Test func theOwnerGetsTheRateAndTheEstimatedInterest() throws {
        let fund = try Self.decode(#"""
        {"status":"OK","scope":"owner","current_amount":471234.56,"declared_amount":450000,"annual_interest_rate":2.5,
         "auto_contribution":{"enabled":true,"amount":10000,"frequency":"biweekly","start_date":"2026-09-01","base_amount":450000,
          "contributions_count":2,"contributions_amount":20000,"estimated_interest":1234.56,"next_date":"2026-11-10","total":471234.56}}
        """#)
        #expect(fund.offersInterestRate && fund.annualInterestRate == Decimal(string: "2.5"))
        #expect(fund.activePlan?.estimatedInterest == Decimal(string: "1234.56"))
    }

    @Test func thePlanBodyCarriesTheBalanceAndTheOwnerRateOnlyWhenGiven() throws {
        let plan = SalvavidasPlanRequest(enabled: true, amount: 10_000, frequency: "weekly", startDate: "2026-11-05", endDate: nil)
        #expect(try Self.body(.plan(plan)) == #"{"auto_contribution":{"amount":10000,"enabled":true,"end_date":null,"frequency":"weekly","start_date":"2026-11-05"}}"#)
        #expect(try Self.body(.plan(plan, currentAmount: 0)).contains(#""current_amount":0"#), "0 is a valid declared balance")
        let withEnd = SalvavidasPlanRequest(enabled: false, amount: 5_000, frequency: "monthly", startDate: "2026-11-05", endDate: "2027-05-05")
        let owner = try Self.body(.plan(withEnd, annualInterestRate: Decimal(string: "2.5")))
        #expect(owner.contains(#""annual_interest_rate":2.5"#) && owner.contains(#""end_date":"2027-05-05""#) && owner.contains(#""enabled":false"#))
        #expect(!(try Self.body(.plan(plan))).contains("annual_interest_rate"), "no rate unless the Owner typed one")
        #expect(SalvavidasUpdate.plan(nil) == nil, "nothing to send")
        #expect(try Self.body(.plan(nil, annualInterestRate: 3)) == #"{"annual_interest_rate":3}"#)
    }

    @Test func invalidPlansAndRatesNeverLeaveTheDevice() async throws {
        let transport = ScriptedTransport([.status(200, #"{"status":"OK","scope":"users"}"#)])
        let api = Self.service(transport)
        let bad: [SalvavidasPlanRequest] = [
            .init(enabled: true, amount: 0, frequency: "weekly", startDate: "2026-11-05", endDate: nil),
            .init(enabled: true, amount: 10, frequency: "daily", startDate: "2026-11-05", endDate: nil),
            .init(enabled: true, amount: 10, frequency: "weekly", startDate: "2026-02-30", endDate: nil),
            .init(enabled: true, amount: 10, frequency: "weekly", startDate: "2026-11-05", endDate: "2026-11-04"),
            .init(enabled: true, amount: Decimal(string: "1000000000")!, frequency: "weekly", startDate: "2026-11-05", endDate: nil),
        ]
        for plan in bad { await #expect(throws: APIError.self) { _ = try await api.updateSalvavidas(.plan(plan)!) } }
        await #expect(throws: APIError.self) { _ = try await api.updateSalvavidas(.plan(nil, annualInterestRate: 51)!) }
        await #expect(throws: APIError.self) { _ = try await api.updateSalvavidas(.plan(nil, annualInterestRate: -1)!) }
        #expect(transport.requests.isEmpty)
        let good = SalvavidasPlanRequest(enabled: true, amount: 10_000, frequency: "weekly", startDate: "2026-11-05", endDate: "2026-11-05")
        _ = try await api.updateSalvavidas(.plan(good)!)
        #expect(transport.requests.first?.httpMethod == "PUT" && transport.requests.first?.url?.path == "/user-product/vip/salvavidas")
    }

    @Test func theRateInputAcceptsBothDecimalMarks() {
        #expect(SalvavidasRateInput.parse("2,5") == Decimal(string: "2.5"))
        #expect(SalvavidasRateInput.parse("2.5 %") == Decimal(string: "2.5"))
        #expect(SalvavidasRateInput.parse("0") == 0)
        #expect(SalvavidasRateInput.parse("50") == 50)
        for bad in ["", "50.01", "-1", "abc", "1.23456", "1,2,3", ".5"] { #expect(SalvavidasRateInput.parse(bad) == nil, "\(bad)") }
    }

    @Test func theFixtureMirrorsTheContract() async throws {
        let backend = FixtureBackend(scenario: .populated, plan: .vip, latency: .zero)
        let user = FixtureBackend.service(backend)
        let plan = SalvavidasPlanRequest(enabled: true, amount: 10_000, frequency: "weekly", startDate: "2026-01-01", endDate: nil)
        // Unknown savings: enabling needs the balance of today; without a situation it cannot be saved.
        await #expect(throws: APIError.self) { _ = try await user.updateSalvavidas(.plan(plan)!) }
        // The rate is the Owner's alone.
        await #expect(throws: APIError.self) { _ = try await user.updateSalvavidas(.plan(nil, annualInterestRate: 2)!) }
        var situation = FinancialProfile()
        situation.incomeType = "fixed"; situation.workDaysPerWeek = 5
        _ = try await user.updateFinancialSituation(situation, idempotencyKey: "op_situation_plan")
        let saved = try await user.updateSalvavidas(.plan(plan, currentAmount: 0)!)
        let active = try #require(saved.activePlan)
        // Declared today: the count starts again from today, so nothing is added yet.
        #expect(saved.declaredAmount == 0 && saved.currentAmount == 0 && active.contributionsCount == 0 && active.total == 0)
        #expect(active.nextDate != nil && saved.annualInterestRate == nil)
        // Turning it off keeps the settings.
        let off = try await user.updateSalvavidas(.plan(SalvavidasPlanRequest(enabled: false, amount: 10_000, frequency: "weekly", startDate: "2026-01-01", endDate: nil))!)
        #expect(off.autoContribution?.isEnabled == false && off.activePlan == nil && off.autoContribution?.amount == 10_000)

        let owner = FixtureBackend.service(FixtureBackend(scenario: .populated, role: .owner, latency: .zero))
        let ownerFund = try await owner.updateSalvavidas(.plan(plan, annualInterestRate: Decimal(string: "2.5"))!)
        #expect(ownerFund.isOwnerScope && ownerFund.annualInterestRate == Decimal(string: "2.5") && ownerFund.activePlan != nil)
        #expect(ownerFund.declaredAmount == 450_000 && ownerFund.currentAmount == 450_000)
        await #expect(throws: APIError.self) { _ = try await owner.updateSalvavidas(.plan(nil, annualInterestRate: 60)!) }
    }

    @Test func theFixtureScheduleCountsLikeTheBackend() throws {
        func day(_ text: String) throws -> Date { try #require(FixtureBackend.parseDay(text)) }
        let weekly: [String: Any] = ["frequency": "weekly", "start_date": "2026-10-01"]
        let dates = FixtureBackend.scheduledDays(weekly, after: try day("2026-09-30"), until: try day("2026-10-22"))
        #expect(dates.map(FixtureBackend.dayString) == ["2026-10-01", "2026-10-08", "2026-10-15", "2026-10-22"])
        // Monthly keeps the day, clamped to the month's end; the end date stops it.
        let monthly: [String: Any] = ["frequency": "monthly", "start_date": "2026-01-31", "end_date": "2026-04-30"]
        let months = FixtureBackend.scheduledDays(monthly, after: try day("2026-01-01"), until: try day("2026-12-31"))
        #expect(months.map(FixtureBackend.dayString) == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"])
        let biweekly: [String: Any] = ["frequency": "biweekly", "start_date": "2026-10-01"]
        #expect(FixtureBackend.scheduledDays(biweekly, after: try day("2026-10-01"), until: try day("2026-10-29")).map(FixtureBackend.dayString) == ["2026-10-15", "2026-10-29"])
    }

    @Test func aSavedPlanSummarizesInOneLine() {
        #expect(SalvavidasAutoContribution.summary(amount: "₡2.500", frequency: "weekly", language: .spanish) == "₡2.500 cada semana")
        #expect(SalvavidasAutoContribution.summary(amount: "₡2,500", frequency: "monthly", language: .english) == "₡2,500 every month")
        #expect(SalvavidasAutoContribution.rateLabel(Decimal(string: "2.5")!, language: .spanish) == "2,5 %")
        #expect(SalvavidasAutoContribution.rateLabel(Decimal(string: "2.5")!, language: .english) == "2.5%")
    }
}
