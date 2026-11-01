import Foundation
import Testing
@testable import DincrCore

/// RT-1 — Retiro in simple words. Android: `RetirementTest.kt`. Synthetic data.
@Suite struct RetirementTests {
    private let colones = MoneyFormat(currency: "CRC", separators: .dotComma)
    private func config(rop: Decimal? = 3_000_000, voluntary: Decimal? = nil, birth: Int? = 1991, age: Int? = 65) -> Retirement.Config {
        Retirement.Config(ropBalance: rop, voluntaryBalance: voluntary, birthYear: birth, retireAge: age)
    }

    @Test func theReferenceGrowsWithAge() {
        #expect(RetirementReading.multiple(age: 24) == nil)
        #expect(RetirementReading.multiple(age: 30) == 1 && RetirementReading.multiple(age: 35) == 2)
        #expect(RetirementReading.multiple(age: 32) == 1.4 && RetirementReading.multiple(age: 70) == 10)
    }

    @Test func belowTheReferenceSaysHowMuchMoreEachMonth() {
        // 35 years old in 2026, ₡500.000 a month: the reference is 2 × 6.000.000 = 12.000.000.
        let lines = RetirementReading.lines(config(), monthlyIncome: 500_000, year: 2026, format: colones, language: .spanish)
        #expect(lines == ["Tenés ₡3.000.000 ahorrado para tu retiro.",
                          "Te faltan 30 años para retirarte a los 65.",
                          "Para tu edad, una referencia común es tener 2 veces tu ingreso anual (₡12.000.000): vas por debajo.",
                          "Si aportás ₡150.000 más al mes, en 5 años cerrás la diferencia."])
    }

    @Test func aboveOrCloseSaySoWithoutAnAction() {
        let above = RetirementReading.lines(config(rop: 10_000_000, voluntary: 3_000_000), monthlyIncome: 500_000, year: 2026, format: colones, language: .spanish)
        #expect(above.last?.hasSuffix(": vas por encima.") == true && above.count == 3)
        let close = RetirementReading.lines(config(rop: 10_000_000), monthlyIncome: 500_000, year: 2026, format: colones, language: .spanish)
        #expect(close.last?.hasSuffix(": vas cerca.") == true)
    }

    @Test func unknownPartsAreLeftOutNeverZero() {
        #expect(RetirementReading.lines(config(rop: nil), monthlyIncome: 500_000, year: 2026, format: colones).isEmpty)
        #expect(RetirementReading.lines(config(birth: nil), monthlyIncome: 500_000, year: 2026, format: colones, language: .spanish).last
                == "Poné tu año de nacimiento para compararlo con tu edad.")
        #expect(RetirementReading.lines(config(), monthlyIncome: nil, year: 2026, format: colones, language: .spanish).count == 2, "no income: no comparison")
        #expect(RetirementReading.lines(config(birth: 2004), monthlyIncome: 500_000, year: 2026, format: colones, language: .spanish).last
                == "Lo importante ahora es empezar y aportar seguido.")
    }

    @Test func anUpdateSendsEveryFieldSoANullClears() throws {
        let body = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(RetirementUpdate(ropBalance: 100, voluntaryBalance: nil, birthYear: 1990, retireAge: 65))) as? [String: Any]
        #expect(body?["rop_balance"] as? Int == 100 && body?["voluntary_balance"] is NSNull && body?["birth_year"] as? Int == 1990)
    }
}
