import Foundation
import Testing
@testable import DincrCore

@Suite struct MoneyFormatTests {
    @Test func colonesUseProfileSeparatorsAndNoDecimals() {
        let format = MoneyFormat(currency: "CRC", separators: .dotComma, placement: .before)
        #expect(format.string(1_234_567) == "₡1.234.567")
        #expect(format.string(18_450, sign: .expense) == "−₡18.450")
        #expect(format.string(432_500, sign: .income) == "+₡432.500")
    }

    @Test func dollarsKeepCentsAndHonorPlacement() {
        let format = MoneyFormat(currency: "USD", separators: .commaDot, placement: .after)
        #expect(format.string(Decimal(string: "1234.5")!) == "1,234.50 $")
    }

    @Test func negativeValuesWithoutSignStillShowMinus() {
        #expect(MoneyFormat().string(-5_000) == "−₡5.000")
    }

    @Test func spokenAmountsAreCompletePhrases() {
        let format = MoneyFormat()
        #expect(format.spoken(18_450, sign: .expense, language: .spanish) == "menos 18450 colones")
        // Display grouping must never reach the screen reader: "257.550" reads as a decimal in English.
        #expect(format.spoken(257_550, language: .english) == "257550 colones")
        #expect(MoneyFormat(currency: "USD").spoken(Decimal(string: "1234.5")!, language: .english) == "1234.5 dollars")
        #expect(format.spoken(1, language: .spanish) == "1 colón")
        #expect(format.spoken(20, sign: .income, language: .english) == "plus 20 colones")
    }

    @Test(arguments: [
        ("18.450", MoneyFormat.Separators.dotComma, Decimal(18_450)),
        ("18.450,75", .dotComma, Decimal(string: "18450.75")!),
        ("1,234.5", .commaDot, Decimal(string: "1234.5")!),
        ("  250 ", .dotComma, Decimal(250)),
        ("1,5", .dotComma, Decimal(string: "1.5")!),
        ("1234567", .commaDot, Decimal(1_234_567)),
    ])
    func parsesUserInput(text: String, separators: MoneyFormat.Separators, expected: Decimal) {
        #expect(AmountInput.parse(text, separators: separators) == expected)
    }

    @Test(arguments: ["", "0", "-5", "abc", "1,2,3", "12e3", "1,5", "12,34,567", "1.5.2", "1,234,56"])
    func rejectsInvalidInput(text: String) {
        #expect(AmountInput.parse(text, separators: .commaDot) == nil)
    }
}
