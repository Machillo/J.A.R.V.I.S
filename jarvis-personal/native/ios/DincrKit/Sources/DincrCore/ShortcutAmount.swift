import Foundation

/// The two currencies a shortcut purchase can carry.
public enum ShortcutCurrency: String, Sendable, CaseIterable, Codable {
    case crc = "CRC"
    case usd = "USD"

    /// The largest purchase a shortcut sends, the backend's own cap (shortcut_capture.MAX_AMOUNT): a typo
    /// or a misread variable beyond it is refused here, not sent. ₡50 000 000 or $100 000.
    public var cap: Decimal {
        switch self {
        case .crc: Decimal(50_000_000)
        case .usd: Decimal(100_000)
        }
    }
}

/// An amount read from the Shortcuts *Transacción* "Monto" variable, ready for the wire.
public struct ShortcutAmount: Sendable, Equatable {
    public let value: Decimal
    public let currency: ShortcutCurrency
    /// Canonical decimal string for the backend (`12500.50`): never a float.
    public let wire: String

    public enum Failure: Error, Sendable, Equatable {
        case empty, unreadable, notPositive, tooLarge, mixedCurrencies

        public func message(_ language: AppLanguage = .current) -> String {
            switch self {
            case .empty: language.pick("Falta el monto de la compra.", "The purchase amount is missing.")
            case .unreadable: language.pick("No entendimos el monto de la compra.", "We couldn’t read the purchase amount.")
            case .notPositive: language.pick("El monto de la compra tiene que ser mayor a cero.", "The purchase amount must be greater than zero.")
            case .tooLarge: language.pick("El monto de la compra es demasiado alto.", "The purchase amount is too high.")
            case .mixedCurrencies: language.pick("El monto trae dos monedas distintas.", "The amount shows two different currencies.")
            }
        }
    }

    /// Reads whatever Shortcuts delivers: a plain number ("4.99", "12500"), or text with a symbol or code
    /// ("₡12.500,00", "CRC 12,500.00", "$4.99", "4,99 US$"). Deterministic rules:
    /// - the currency comes from the text (₡ / CRC → CRC; $ / US$ / USD → USD); otherwise `fallback`;
    /// - the last '.' or ',' followed by one or two digits is the decimal separator; every other
    ///   separator groups thousands (groups of exactly three digits, the first of one to three);
    /// - anything else (letters, two numbers, a separator used both ways) is unreadable: refused, never guessed.
    public static func parse(_ text: String, fallback: ShortcutCurrency) -> Result<ShortcutAmount, Failure> {
        var rest = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !rest.isEmpty else { return .failure(.empty) }

        // Currency marks, longest first ("US$" before "$").
        var found: Set<ShortcutCurrency> = []
        for (mark, currency) in [("US$", ShortcutCurrency.usd), ("USD", .usd), ("CRC", .crc), ("₡", .crc), ("$", .usd)] {
            if rest.range(of: mark, options: .caseInsensitive) != nil {
                found.insert(currency)
                rest = rest.replacingOccurrences(of: mark, with: "", options: .caseInsensitive)
            }
        }
        guard found.count <= 1 else { return .failure(.mixedCurrencies) }
        let currency = found.first ?? fallback

        // Spaces (also no-break and thin spaces) only separate the mark or group digits.
        rest = String(rest.unicodeScalars.filter { !CharacterSet.whitespacesAndNewlines.contains($0) && !["\u{00A0}", "\u{202F}", "\u{2009}"].contains($0) })
        var negative = false
        if let first = rest.first, first == "-" || first == "−" { negative = true; rest.removeFirst() }
        if rest.first == "+" { rest.removeFirst() }

        guard let number = canonical(rest) else { return .failure(.unreadable) }
        guard let value = Decimal(string: number, locale: Locale(identifier: "en_US_POSIX")) else { return .failure(.unreadable) }
        guard !negative, value > 0 else { return .failure(.notPositive) }
        guard value <= currency.cap else { return .failure(.tooLarge) }
        return .success(ShortcutAmount(value: value, currency: currency, wire: number))
    }

    /// "12.500,00" → "12500.00"; nil when the text is not one well-formed number of ASCII digits.
    static func canonical(_ text: String) -> String? {
        let separators: Set<Character> = [".", ","]
        guard let first = text.first, let last = text.last, first.isASCIIDigit, last.isASCIIDigit,
              text.allSatisfy({ $0.isASCIIDigit || separators.contains($0) }) else { return nil }

        var integer = text
        var fraction = ""
        if let index = text.lastIndex(where: { separators.contains($0) }) {
            let tail = text[text.index(after: index)...]
            if (1...2).contains(tail.count) {
                // The decimal separator: it must appear once, and any grouping uses the other character.
                let mark = text[index]
                integer = String(text[..<index])
                fraction = String(tail)
                guard !integer.contains(mark), !integer.isEmpty else { return nil }
            }
        }

        let groupMarks = Set(integer.filter { separators.contains($0) })
        guard groupMarks.count <= 1 else { return nil }
        if let mark = groupMarks.first {
            let groups = integer.split(separator: mark, omittingEmptySubsequences: false)
            guard let head = groups.first, (1...3).contains(head.count), groups.dropFirst().allSatisfy({ $0.count == 3 }) else { return nil }
            integer = groups.joined()
        }
        guard integer.allSatisfy(\.isASCIIDigit), !integer.isEmpty else { return nil }

        let trimmed = String(integer.drop { $0 == "0" })
        let whole = trimmed.isEmpty ? "0" : trimmed
        guard whole.count <= 10 else { return nil }
        return fraction.isEmpty ? whole : "\(whole).\(fraction)"
    }
}

extension Character {
    var isASCIIDigit: Bool { isASCII && isNumber }
}
