import Foundation

/// Presentation-only money formatting from the user's profile preferences
/// (`base_currency`, `number_format`, `currency_placement` set in profile setup).
/// It never converts between currencies. Display rounding (colones without decimals) is visual
/// only: editable text uses `inputText`, which keeps every stored digit.
public struct MoneyFormat: Sendable, Equatable {
    public enum Separators: String, Sendable { case dotComma = "dot_comma", commaDot = "comma_dot" }
    public enum Placement: String, Sendable { case before, after }
    public enum Sign: Sendable { case none, income, expense }

    public let currency: String
    public let separators: Separators
    public let placement: Placement

    public init(currency: String = "CRC", separators: Separators = .dotComma, placement: Placement = .before) {
        self.currency = currency.uppercased(); self.separators = separators; self.placement = placement
    }

    public init(profile: Profile?) {
        self.init(
            currency: profile?.baseCurrency ?? "CRC",
            separators: Separators(rawValue: profile?.numberFormat ?? "") ?? .dotComma,
            placement: Placement(rawValue: profile?.currencyPlacement ?? "") ?? .before
        )
    }

    public var symbol: String {
        switch currency {
        case "CRC": "₡"
        case "USD": "$"
        case "EUR": "€"
        default: currency
        }
    }

    /// Colones are shown without decimals (as in the Capacitor app); other currencies with 2.
    public var fractionDigits: Int { currency == "CRC" ? 0 : 2 }

    public func string(_ amount: Decimal, sign: Sign = .none, currency override: String? = nil) -> String {
        let format = override.map { MoneyFormat(currency: $0, separators: separators, placement: placement) } ?? self
        let magnitude = format.digits(abs(amount))
        // A currency code (legacy bases such as ARS) is a word, so it gets a space: "ARS 1.234,00".
        let gap = format.symbol.count > 1 ? " " : ""
        let body = format.placement == .before ? "\(format.symbol)\(gap)\(magnitude)" : "\(magnitude) \(format.symbol)"
        let prefix: String = switch sign {
        case .income: "+"
        case .expense: "−"
        case .none: amount < 0 ? "−" : ""
        }
        return prefix + body
    }

    /// A complete phrase for VoiceOver, e.g. "menos 18.450 colones". `currency` names the unit
    /// when the amount is not in the base currency, exactly like `string(_:sign:currency:)`.
    public func spoken(_ amount: Decimal, sign: Sign = .none, currency override: String? = nil, language: AppLanguage = .current) -> String {
        if let override, override.uppercased() != currency {
            return MoneyFormat(currency: override, separators: separators, placement: placement).spoken(amount, sign: sign, language: language)
        }
        let negative = sign == .expense || (sign == .none && amount < 0)
        let positive = sign == .income
        // Screen readers read display grouping literally ("257.550" can become "257 point 55" in
        // English), so the spoken form uses ungrouped digits and the language's decimal mark.
        let number = spokenDigits(abs(amount), language: language)
        let unit = unitName(language: language, plural: abs(amount) != 1)
        let lead = negative ? language.pick("menos ", "minus ") : positive ? language.pick("más ", "plus ") : ""
        return "\(lead)\(number) \(unit)"
    }

    /// The stored amount as the user would type it (their separators, no symbol, no rounding),
    /// for prefilling an edit form. `AmountInput.parse` reads it back to the same value.
    public func inputText(_ amount: Decimal) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.minimumFractionDigits = 0
        formatter.maximumFractionDigits = AmountInput.maxFractionDigits
        formatter.roundingMode = .halfUp
        formatter.usesGroupingSeparator = true
        formatter.groupingSize = 3
        formatter.groupingSeparator = separators == .dotComma ? "." : ","
        formatter.decimalSeparator = separators == .dotComma ? "," : "."
        return formatter.string(from: abs(amount) as NSDecimalNumber) ?? "\(abs(amount))"
    }

    func digits(_ value: Decimal) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.minimumFractionDigits = fractionDigits
        formatter.maximumFractionDigits = fractionDigits
        // Half away from zero, like the Capacitor app's Intl.NumberFormat (₡2,5 → ₡3).
        formatter.roundingMode = .halfUp
        formatter.usesGroupingSeparator = true
        formatter.groupingSize = 3
        formatter.groupingSeparator = separators == .dotComma ? "." : ","
        formatter.decimalSeparator = separators == .dotComma ? "," : "."
        return formatter.string(from: value as NSDecimalNumber) ?? "\(value)"
    }

    func spokenDigits(_ value: Decimal, language: AppLanguage) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.roundingMode = .halfUp
        formatter.usesGroupingSeparator = false
        formatter.minimumFractionDigits = 0
        formatter.maximumFractionDigits = fractionDigits
        formatter.decimalSeparator = language == .spanish ? "," : "."
        return formatter.string(from: value as NSDecimalNumber) ?? "\(value)"
    }

    func unitName(language: AppLanguage, plural: Bool) -> String {
        switch (currency, language) {
        case ("CRC", .spanish): plural ? "colones" : "colón"
        case ("CRC", .english): plural ? "colones" : "colón"
        case ("USD", .spanish): plural ? "dólares" : "dólar"
        case ("USD", .english): plural ? "dollars" : "dollar"
        case ("EUR", _): plural ? "euros" : "euro"
        default: currency
        }
    }
}

/// Parses what the user typed in an amount field, following their separator preference.
/// Returns nil for anything that is not an unambiguous positive amount: a wrong value is worse
/// than asking again, so nothing is guessed.
public enum AmountInput {
    /// Money never has more than two decimals. It also makes "1.000" (comma_dot) and "1,000"
    /// (dot_comma) invalid instead of silently meaning one.
    public static let maxFractionDigits = 2
    /// Twelve integer digits (below a trillion) is far above any personal amount and keeps
    /// accidental pastes out of the ledger.
    public static let maxIntegerDigits = 12

    public static func parse(_ text: String, separators: MoneyFormat.Separators) -> Decimal? {
        let trimmed = text.replacingOccurrences(of: " ", with: "")
        guard !trimmed.isEmpty else { return nil }
        let grouping: Character = separators == .dotComma ? "." : ","
        let decimal: Character = separators == .dotComma ? "," : "."
        guard trimmed.allSatisfy({ $0.isASCII && ($0.isNumber || $0 == grouping || $0 == decimal) }) else { return nil }
        let halves = trimmed.split(separator: decimal, omittingEmptySubsequences: false)
        guard halves.count <= 2 else { return nil }
        let integer = halves[0]
        let fraction = halves.count == 2 ? halves[1] : ""
        guard !integer.isEmpty, !fraction.contains(grouping), fraction.count <= maxFractionDigits else { return nil }
        // Grouping must be real thousands groups ("18.450"), never a mistyped decimal
        // ("1,5" in comma_dot would otherwise silently become 15).
        let groups = integer.split(separator: grouping, omittingEmptySubsequences: false)
        if groups.count > 1 {
            guard let first = groups.first, (1...3).contains(first.count),
                  groups.dropFirst().allSatisfy({ $0.count == 3 }) else { return nil }
        }
        let integerDigits = groups.joined().drop(while: { $0 == "0" })
        guard integerDigits.count <= maxIntegerDigits else { return nil }
        let digits = groups.joined() + (fraction.isEmpty ? "" : "." + fraction)
        guard let value = Decimal(string: digits, locale: Locale(identifier: "en_US_POSIX")), value > 0 else { return nil }
        return value
    }
}
