import Foundation

/// The invented account behind the App Store screenshots (store-assets/), served by
/// `FixtureDincrService` as `.store` (`-DincrFixtures store`, Debug only). The Swift twin of
/// Android's `StoreSample.kt`, with the same people, dates and amounts:
/// - a fixed month (September 2026, paydays on the 15th and 28th), so the images do not depend
///   on the capture day;
/// - six months of history, so the chart is full;
/// - a first name, a plan bought in the store (not a courtesy grant);
/// - text in the app's language, as the real backend localizes with Accept-Language. User-entered
///   text (descriptions, names) is what an English- or Spanish-speaking user would type.
/// The dashboard is computed from these movements and debts, so every figure agrees.
enum StoreSample {
    static let month = "2026-09"
    static let paycheck: Decimal = 432_500

    static func profile(plan: PlanTier, language: AppLanguage) -> Profile {
        Profile(
            id: 4201, email: "ana.demo@example.com", displayName: "Ana", role: "user",
            planSelected: true, profileSetupCompleted: true, baseCurrency: "CRC",
            numberFormat: language.pick("dot_comma", "comma_dot"), currencyPlacement: "before",
            subscription: .init(plan: plan.rawValue, status: "active", accessSource: "self_service"),
            legal: .init(required: false, termsVersion: "2026-09", privacyVersion: "2026-09")
        )
    }

    static func movements(language l: AppLanguage) -> [Movement] {
        let food = l.pick("Comida", "Food"), transport = l.pick("Transporte", "Transportation")
        let utilities = l.pick("Servicios", "Utilities"), housing = l.pick("Vivienda", "Housing")
        let health = l.pick("Salud", "Health"), restaurants = l.pick("Restaurantes", "Restaurants")
        let entertainment = l.pick("Entretenimiento", "Entertainment"), shopping = l.pick("Compras", "Shopping")
        let groceries = l.pick("Supermercado", "Groceries"), gas = l.pick("Gasolina", "Gas")
        let pharmacy = l.pick("Farmacia", "Pharmacy"), rent = l.pick("Alquiler", "Rent")
        var id = 0
        var rows: [Movement] = []
        func income(_ date: String) {
            id += 1
            rows.append(Movement(movementId: "salary:\(id)", sourceId: id, origin: "salary", transactionDate: date,
                                 description: l.pick("Salario quincenal", "Paycheck"), amount: paycheck, transactionType: .income, category: l.pick("Salario", "Salary")))
        }
        func expense(_ date: String, _ description: String, _ amount: Decimal, _ category: String) {
            id += 1
            rows.append(Movement(movementId: "expense:\(id)", sourceId: id, origin: "expense", transactionDate: date,
                                 description: description, amount: amount, transactionType: .expense, category: category))
        }
        func day(_ month: String, _ day: Int) -> String { String(format: "%@-%02d", month, day) }
        let current = month
        income(day(current, 15)); income(day(current, 28))
        expense(day(current, 2), rent, 210_000, housing)
        expense(day(current, 4), groceries, 46_300, food)
        expense(day(current, 6), l.pick("Luz y agua", "Power and water"), 31_800, utilities)
        expense(day(current, 8), l.pick("Internet del hogar", "Home internet"), 24_900, utilities)
        expense(day(current, 11), gas, 30_000, transport)
        expense(day(current, 13), pharmacy, 9_800, health)
        expense(day(current, 17), groceries, 52_450, food)
        expense(day(current, 21), gas, 25_000, transport)
        expense(day(current, 24), l.pick("Almuerzo", "Lunch"), 8_500, restaurants)
        expense(day(current, 26), groceries, 38_900, food)
        expense(day(current, 27), l.pick("Café", "Coffee"), 2_300, restaurants)
        id += 1
        // A subscription paid in dollars and converted at the entry's rate (#269).
        rows.append(Movement(movementId: "expense:\(id)", sourceId: id, origin: "expense", transactionDate: day(current, 19),
                             description: l.pick("Suscripción de streaming", "Streaming subscription"), amount: Decimal(string: "5075.00")!,
                             transactionType: .expense, category: entertainment, originalAmount: 10, originalCurrency: "USD", exchangeRate: Decimal(string: "507.5")!))
        let bills = l.pick("Luz, agua e internet", "Power, water and internet")
        let movies = l.pick("Cine", "Movies"), restaurant = l.pick("Restaurante", "Restaurant")
        let doctor = l.pick("Consulta médica", "Doctor visit"), clothes = l.pick("Ropa", "Clothes")
        let history: [(String, [(String, Decimal)])] = [
            ("2026-08", [(groceries, 142_300), (bills, 58_000), (gas, 61_500), (pharmacy, 18_000), (movies, 27_400)]),
            ("2026-07", [(groceries, 151_800), (bills, 56_500), (gas, 64_200), (restaurant, 33_900), (movies, 22_000)]),
            ("2026-06", [(groceries, 138_900), (bills, 59_800), (gas, 58_700), (doctor, 42_500), (clothes, 36_000)]),
            ("2026-05", [(groceries, 147_600), (bills, 57_200), (gas, 66_100), (restaurant, 28_400), (movies, 19_500)]),
            ("2026-04", [(groceries, 144_100), (bills, 58_400), (gas, 60_900), (clothes, 41_200), (pharmacy, 12_800)]),
        ]
        let fixed = [food, utilities, transport]
        for (month, items) in history {
            income(day(month, 15)); income(day(month, 28))
            expense(day(month, 2), rent, 210_000, housing)
            for (position, item) in items.enumerated() {
                let category: String
                if position < fixed.count { category = fixed[position] }
                else if item.0 == pharmacy || item.0 == doctor { category = health }
                else if item.0 == restaurant { category = restaurants }
                else if item.0 == clothes { category = shopping }
                else { category = entertainment }
                expense(day(month, 5 + position * 4), item.0, item.1, category)
            }
        }
        return rows
    }

    static func debts(language l: AppLanguage) -> [Debt] {
        [
            Debt(id: 1, name: l.pick("Tarjeta principal", "Main card"), debtType: "credit_card", totalAmount: 750_000, remainingAmount: 585_000,
                 monthlyPayment: 45_000, interestRate: 36, paymentDay: 3, nextPaymentDate: "2026-10-03", progressPercent: 22),
            Debt(id: 2, name: l.pick("Préstamo del carro", "Car loan"), debtType: "loan", totalAmount: 2_400_000, remainingAmount: 1_560_000,
                 monthlyPayment: 50_000, interestRate: Decimal(string: "14.5")!, paymentDay: 1, progressPercent: 35),
        ]
    }

    static func goals(language l: AppLanguage) -> [Goal] {
        [
            Goal(id: 3, name: l.pick("Fondo de emergencia", "Emergency fund"), targetAmount: 600_000, currentAmount: 240_000, targetDate: "2027-05-28", priority: "high"),
            Goal(id: 4, name: l.pick("Vacaciones", "Vacation"), targetAmount: 300_000, currentAmount: 75_000, targetDate: "2027-06-01"),
        ]
    }

    /// What `GET /user-product/free/dashboard` returns for these rows: six months, the current one last.
    static func dashboard(movements: [Movement], debts: [Debt]) -> FreeDashboard {
        func totals(_ period: String) -> (income: Decimal, expenses: Decimal) {
            let rows = movements.filter { ($0.transactionDate ?? "").hasPrefix(period) }
            let income = rows.filter { $0.transactionType == .income }.reduce(Decimal(0)) { $0 + $1.amount }
            let expenses = rows.filter { $0.transactionType == .expense }.reduce(Decimal(0)) { $0 + $1.amount }
            return (income, expenses)
        }
        var byCategory: [String: Decimal] = [:]
        for row in movements where row.transactionType == .expense && (row.transactionDate ?? "").hasPrefix(month) {
            byCategory[row.category ?? "", default: 0] += row.amount
        }
        let categories = byCategory.sorted { $0.value == $1.value ? $0.key < $1.key : $0.value > $1.value }
            .map { CategoryAmount(category: $0.key, amount: $0.value) }
        let history = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", month].map { period -> MonthTotals in
            let t = totals(period)
            return MonthTotals(month: period, income: t.income, expenses: t.expenses, debtPaid: 0, balance: t.income - t.expenses)
        }
        let now = totals(month)
        let debtBalance = debts.reduce(Decimal(0)) { $0 + ($1.remainingAmount ?? 0) }
        return FreeDashboard(month: month, income: now.income, expenses: now.expenses, debtPaid: 0, debtBalance: debtBalance,
                             balance: now.income - now.expenses, availableAfterCommitments: now.income - now.expenses,
                             categories: categories, monthlyHistory: history)
    }
}
