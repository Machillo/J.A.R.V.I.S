import Foundation

// RT-1 — Plan → Retiro (VIP and the Owner): what the user has put aside for retirement (ROP and a
// voluntary pension, declared by hand; `GET/PUT /user-product/vip/retirement`) read in simple words:
// how much, how many years are left, and how it compares with a common age reference (a multiple of
// the yearly income, from the normal month). Fixed rules, not investment advice. Unknown is never 0:
// without a balance there is no reading; without an age or an income that comparison is left out.
// Android twin: `Retirement.kt`.

public struct Retirement: Decodable, Sendable, Equatable {
    public struct Config: Decodable, Sendable, Equatable {
        public let ropBalance: Decimal?
        public let voluntaryBalance: Decimal?
        public let birthYear: Int?
        public let retireAge: Int?

        public init(ropBalance: Decimal?, voluntaryBalance: Decimal?, birthYear: Int?, retireAge: Int?) {
            self.ropBalance = ropBalance; self.voluntaryBalance = voluntaryBalance; self.birthYear = birthYear; self.retireAge = retireAge
        }
    }
    public let config: Config
}

/// `PUT /user-product/vip/retirement`: every field is sent (a null clears it).
public struct RetirementUpdate: Encodable, Sendable, Equatable {
    public let ropBalance: Decimal?
    public let voluntaryBalance: Decimal?
    public let birthYear: Int?
    public let retireAge: Int?

    public init(ropBalance: Decimal?, voluntaryBalance: Decimal?, birthYear: Int?, retireAge: Int?) {
        self.ropBalance = ropBalance; self.voluntaryBalance = voluntaryBalance; self.birthYear = birthYear; self.retireAge = retireAge
    }

    enum CodingKeys: String, CodingKey { case ropBalance, voluntaryBalance, birthYear, retireAge }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(ropBalance, forKey: .ropBalance)
        try c.encode(voluntaryBalance, forKey: .voluntaryBalance)
        try c.encode(birthYear, forKey: .birthYear)
        try c.encode(retireAge, forKey: .retireAge)
    }
}

extension DincrService {
    public func retirement() async throws -> Retirement { try await client.get("/user-product/vip/retirement") }

    public func updateRetirement(_ update: RetirementUpdate) async throws -> Retirement {
        try await client.send("PUT", "/user-product/vip/retirement", body: update)
    }
}

public enum RetirementReading {
    /// A common reference: savings for retirement as a multiple of the yearly income, by age.
    static let reference: [(age: Int, multiple: Double)] = [(25, 0.5), (30, 1), (35, 2), (40, 3), (45, 4), (50, 6), (55, 7), (60, 8), (67, 10)]

    public static func multiple(age: Int) -> Double? {
        guard age >= reference[0].age else { return nil }
        if age >= reference.last!.age { return reference.last!.multiple }
        for (low, high) in zip(reference, reference.dropFirst()) where age <= high.age {
            return low.multiple + (high.multiple - low.multiple) * Double(age - low.age) / Double(high.age - low.age)
        }
        return nil
    }

    /// The reading in short lines; empty without any balance.
    public static func lines(_ config: Retirement.Config, monthlyIncome: Decimal?, year: Int, format: MoneyFormat,
                             language: AppLanguage = .current) -> [String] {
        let parts = [config.ropBalance, config.voluntaryBalance].compactMap { $0 }
        guard !parts.isEmpty else { return [] }
        let total = parts.reduce(0, +)
        var lines = [language.pick("Tenés \(format.string(total)) ahorrado para tu retiro.", "You have \(format.string(total)) saved for retirement.")]
        guard let birth = config.birthYear else {
            lines.append(language.pick("Poné tu año de nacimiento para compararlo con tu edad.", "Add your year of birth to compare it with your age."))
            return lines
        }
        let age = year - birth
        let retireAge = config.retireAge ?? 65
        if retireAge > age {
            lines.append(language.pick("Te faltan \(retireAge - age) años para retirarte a los \(retireAge).", "\(retireAge - age) years are left until you retire at \(retireAge)."))
        }
        guard let multiple = multiple(age: age) else {
            lines.append(language.pick("Lo importante ahora es empezar y aportar seguido.", "What matters now is starting and contributing regularly."))
            return lines
        }
        guard let income = monthlyIncome, income > 0 else { return lines }
        let target = income * 12 * Decimal(multiple)
        let times = String(format: "%.1f", multiple).replacingOccurrences(of: ".0", with: "")
        let shownTimes = language == .spanish ? times.replacingOccurrences(of: ".", with: ",") : times
        let reference = language.pick("Para tu edad, una referencia común es tener \(shownTimes) veces tu ingreso anual (\(format.string(target)))",
                                      "For your age, a common reference is \(shownTimes) times your yearly income (\(format.string(target)))")
        if total >= target {
            lines.append(reference + language.pick(": vas por encima.", ": you are above it."))
        } else if total >= target * Decimal(0.8) {
            lines.append(reference + language.pick(": vas cerca.", ": you are close."))
        } else {
            lines.append(reference + language.pick(": vas por debajo.", ": you are below it."))
            var gap = (target - total) / 60, rounded = Decimal()
            NSDecimalRound(&rounded, &gap, 0, .up)
            lines.append(language.pick("Si aportás \(format.string(rounded)) más al mes, en 5 años cerrás la diferencia.",
                                       "If you add \(format.string(rounded)) more a month, you close the gap in 5 years."))
        }
        return lines
    }
}
