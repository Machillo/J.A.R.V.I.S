import Foundation
import Testing
@testable import DincrCore

/// NT-1 — the reminders the phone schedules: the day before a debt's or fixed expense's day, the
/// day of a Salvavidas contribution, and the first day of each month. Only recorded dates; nothing
/// guessed. Android: `RemindersTest.kt`. Synthetic data.
@Suite struct RemindersTests {
    private let calendar = Calendar(identifier: .gregorian)
    private let colones = MoneyFormat(currency: "CRC", separators: .dotComma)

    private func date(_ year: Int, _ month: Int, _ day: Int) -> Date { calendar.date(from: DateComponents(year: year, month: month, day: day))! }
    private func debts(_ json: String) throws -> [Debt] { try APIClient.decoder.decode([Debt].self, from: Data(json.utf8)) }
    private func saving(_ json: String) throws -> SalvavidasAutoContribution {
        try APIClient.decoder.decode(SalvavidasAutoContribution.self, from: Data(json.utf8))
    }
    private func day(_ reminder: Reminders.Reminder) -> String {
        String(format: "%04d-%02d-%02d", reminder.date.year!, reminder.date.month!, reminder.date.day!)
    }

    @Test func onlyActiveDebtsWithAPaymentDayGiveReminders() throws {
        let list = try debts(#"""
        [{"id":1,"name":"Préstamo","remaining_amount":500000,"monthly_payment":45000,"payment_day":15},
         {"id":2,"name":"Pagada","remaining_amount":0,"monthly_payment":10000,"payment_day":10},
         {"id":3,"name":"Sin día","remaining_amount":100000,"monthly_payment":10000}]
        """#)
        #expect(Reminders.bills(debts: list).map(\.id) == ["debt-1"])
    }

    @Test func theDayBeforeEachDueDayInsideTheWindow() throws {
        let bills = [Reminders.Bill(id: "debt-1", kind: .debt, name: "Préstamo", amount: 45_000, day: 15),
                     Reminders.Bill(id: "fixed-7", kind: .fixed, name: "Internet", amount: nil, day: 31)]
        let plan = Reminders.plan(today: date(2026, 11, 1), bills: bills, saving: nil, days: 35, format: colones, language: .spanish)
        let byId = plan.filter { !$0.id.contains(".month.") }
        // 14 Nov and 14 Dec are outside? 14 Dec is day 43: outside. 31 Nov → 30 Nov, so the day before is 29 Nov.
        #expect(byId.map(day) == ["2026-11-14", "2026-11-29"])
        #expect(byId[0].title == "Mañana vence una cuota" && byId[0].body == "Préstamo (₡45.000). Tenela lista.")
        #expect(byId[1].title == "Mañana se paga un gasto fijo" && byId[1].body == "Internet.")
        #expect(byId.allSatisfy { $0.date.hour == 9 })
    }

    @Test func aDueDayAlreadyPassedThisMonthIsRemindedNextMonth() {
        let bills = [Reminders.Bill(id: "debt-1", kind: .debt, name: "Préstamo", amount: nil, day: 5)]
        let plan = Reminders.plan(today: date(2026, 11, 10), bills: bills, saving: nil, format: colones, language: .spanish)
        #expect(plan.filter { $0.id.hasPrefix("dincr.reminder.debt") }.map(day) == ["2026-12-04"])
    }

    @Test func theSalvavidasContributionDays() throws {
        let weekly = try saving(#"{"enabled":true,"amount":2500,"frequency":"weekly","start_date":"2026-10-03"}"#)
        let plan = Reminders.plan(today: date(2026, 11, 1), bills: [], saving: weekly, days: 14, format: colones, language: .spanish)
        let contributions = plan.filter { $0.id.contains("salvavidas") }
        #expect(contributions.map(day) == ["2026-11-07", "2026-11-14"])
        #expect(contributions[0].body == "₡2.500 para tu Salvavidas.")
        let off = try saving(#"{"enabled":false,"amount":2500,"frequency":"weekly","start_date":"2026-10-03"}"#)
        #expect(Reminders.plan(today: date(2026, 11, 1), bills: [], saving: off, days: 14, format: colones).isEmpty)
    }

    @Test func theFirstDayOfTheNextMonthSaysTheMonthClosed() {
        let plan = Reminders.plan(today: date(2026, 11, 20), bills: [], saving: nil, format: colones, language: .spanish)
        #expect(plan.map(day) == ["2026-12-01"])
        #expect(plan[0].title == "Tu mes cerró")
    }

    @Test func neverMoreThanTheLimitAndEarliestFirst() {
        let bills = (1...40).map { Reminders.Bill(id: "fixed-\($0)", kind: .fixed, name: "G\($0)", amount: nil, day: ($0 % 28) + 1) }
        let plan = Reminders.plan(today: date(2026, 11, 1), bills: bills, saving: nil, days: 60, format: colones)
        #expect(plan.count == Reminders.limit)
        #expect(plan.map(day) == plan.map(day).sorted())
        #expect(Set(plan.map(\.id)).count == plan.count, "ids are unique")
    }
}
