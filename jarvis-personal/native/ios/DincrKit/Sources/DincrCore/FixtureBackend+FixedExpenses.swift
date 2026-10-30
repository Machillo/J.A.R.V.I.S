import Foundation

// The fixture backend's Plan → Gastos fijos routes for the Owner (Debug demos and tests only). Same
// shapes and access rule as FastAPI (`finance/fixed_expenses.py`): `/finance/*` admits only the
// verified Owner (INTERNAL_ONLY); DELETE deactivates the row. Every name and amount is invented
// (CLAUDE.md §4.F).

struct FixtureFixedExpense {
    let id: Int
    var name: String
    var category: String
    var amount: Decimal
    var intervalMonths: Int
    var dueDay: Int?
    var isActive = true

    static let seed: [FixtureFixedExpense] = [
        FixtureFixedExpense(id: 9101, name: "Internet de ejemplo", category: "Servicios", amount: 24_900, intervalMonths: 1, dueDay: 8),
        FixtureFixedExpense(id: 9102, name: "Gimnasio de ejemplo", category: "Salud", amount: 30_000, intervalMonths: 1, dueDay: 15),
        FixtureFixedExpense(id: 9103, name: "Seguro de ejemplo", category: "Seguros", amount: 60_000, intervalMonths: 2, dueDay: nil),
    ]

    var json: [String: Any] {
        ["id": id, "name": name, "category": category, "expected_amount": FixtureBackend.number(amount), "currency": "CRC",
         "frequency": "monthly", "interval_months": intervalMonths, "due_day": dueDay ?? NSNull(), "is_active": isActive]
    }
}

extension FixtureBackend {
    func fixedExpensesRoute(_ method: String, _ path: String, _ body: [String: Any]) -> Answer? {
        guard path == "/finance/fixed-expenses" || path.hasPrefix("/finance/fixed-expenses/") else { return nil }
        guard profile["role"] as? String == "owner" else { return error(403, "No tienes permisos para realizar esta acción.") }
        let id = Int(path.split(separator: "/").last ?? "")
        switch method {
        case "GET" where path == "/finance/fixed-expenses":
            return ok(ownerFixedExpenses.filter(\.isActive).sorted { ($0.dueDay ?? 99, $0.name) < ($1.dueDay ?? 99, $1.name) }.map(\.json))
        case "POST" where path == "/finance/fixed-expenses":
            let name = (body["name"] as? String ?? "").trimmingCharacters(in: .whitespaces)
            guard !name.isEmpty else { return error(422, "Falta el nombre.") }
            // Same name: the backend updates and reactivates that row instead of adding another.
            let row = FixtureFixedExpense(id: ownerFixedExpenses.first { $0.name == name }?.id ?? nextId(), name: name,
                                          category: body["category"] as? String ?? "Gastos fijos", amount: decimal(body["expected_amount"]) ?? 0,
                                          intervalMonths: body["interval_months"] as? Int ?? 1, dueDay: body["due_day"] as? Int)
            ownerFixedExpenses.removeAll { $0.id == row.id }
            ownerFixedExpenses.append(row)
            return ok(row.json)
        case "PUT":
            guard let id, let index = ownerFixedExpenses.firstIndex(where: { $0.id == id }) else { return ok(NSNull()) }
            if let name = body["name"] as? String { ownerFixedExpenses[index].name = name }
            if let category = body["category"] as? String { ownerFixedExpenses[index].category = category }
            if let amount = decimal(body["expected_amount"]) { ownerFixedExpenses[index].amount = amount }
            if let interval = body["interval_months"] as? Int { ownerFixedExpenses[index].intervalMonths = interval }
            if let day = body["due_day"] as? Int { ownerFixedExpenses[index].dueDay = day }
            return ok(ownerFixedExpenses[index].json)
        case "DELETE":
            guard let id, let index = ownerFixedExpenses.firstIndex(where: { $0.id == id }) else { return ok(["status": "OK", "item": NSNull()]) }
            ownerFixedExpenses[index].isActive = false
            return ok(["status": "OK", "message": "Gasto fijo desactivado.", "item": ownerFixedExpenses[index].json])
        default:
            return nil
        }
    }
}
