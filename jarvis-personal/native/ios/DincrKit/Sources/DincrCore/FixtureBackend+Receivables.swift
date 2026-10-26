import Foundation

// The fixture backend's JARVIS → Control de dinero routes (Debug demos and tests only). Same shapes
// and access rule as FastAPI: `/finance/*` admits only the verified Owner (INTERNAL_ONLY). A write
// the backend refuses answers 200 with `status` ≠ "OK", as the real one does. Every name and amount
// is invented (CLAUDE.md §4.F).

/// One person who owes the Owner money, with their charges and payments.
struct FixtureReceivable {
    struct Entry { let id: Int; let type: String; let amount: Decimal; let description: String; let date: String; let source: String }
    let id: Int
    let name: String
    var carried: Decimal
    var entries: [Entry]

    static let seed: [FixtureReceivable] = [
        FixtureReceivable(id: 7001, name: "Ana de ejemplo", carried: 0, entries: [
            Entry(id: 7101, type: "charge", amount: 35_000, description: "Cena compartida", date: "2026-10-02", source: "manual_purchase")]),
        FixtureReceivable(id: 7002, name: "Luis de ejemplo", carried: 20_000, entries: [
            Entry(id: 7102, type: "charge", amount: 15_000, description: "Compra con tarjeta adicional", date: "2026-10-04", source: "additional_card_auto"),
            Entry(id: 7103, type: "payment", amount: 10_000, description: "Pago en efectivo", date: "2026-10-10", source: "cash_collection")]),
    ]

    var charges: Decimal { entries.filter { $0.type == "charge" }.reduce(0) { $0 + $1.amount } }
    var payments: Decimal { entries.filter { $0.type == "payment" }.reduce(0) { $0 + $1.amount } }
    var due: Decimal { carried + charges - payments }
    var status: String { due < 0 ? "credit" : due == 0 ? "completed" : payments > 0 ? "partial" : "pending" }
}

extension FixtureBackend {
    private var receivablesAllowed: Bool { profile["role"] as? String == "owner" }

    func receivablesRoute(_ method: String, _ path: String, _ body: [String: Any]) -> Answer? {
        guard path.hasPrefix("/finance/receivables") else { return recordsRoute(method, path, body) }
        guard receivablesAllowed else { return error(403, "No tienes permisos para realizar esta acción.") }
        switch method {
        case "GET" where path == "/finance/receivables":
            return ok(receivablesReport())
        case "POST" where path == "/finance/receivables/entries":
            let name = (body["person_name"] as? String ?? "").trimmingCharacters(in: .whitespaces)
            guard !name.isEmpty, let amount = decimal(body["amount"]), amount > 0 else {
                return ok(["status": "ERROR", "message": "Persona y monto mayor a cero requeridos."])
            }
            let entry = FixtureReceivable.Entry(id: nextId(), type: "charge", amount: amount, description: body["description"] as? String ?? "",
                                                date: day(0), source: "manual_\(body["entry_kind"] as? String ?? "purchase")")
            if let index = ownerReceivables.firstIndex(where: { $0.name.lowercased() == name.lowercased() }) {
                ownerReceivables[index].entries.insert(entry, at: 0)
            } else {
                ownerReceivables.append(FixtureReceivable(id: nextId(), name: name, carried: 0, entries: [entry]))
            }
            return ok(["status": "OK"])
        case "POST" where path.hasSuffix("/payments"):
            let id = Int(path.split(separator: "/").dropLast().last ?? "") ?? -1
            guard let index = ownerReceivables.firstIndex(where: { $0.id == id }) else {
                return ok(["status": "NOT_FOUND", "message": "Cuenta por cobrar no encontrada."])
            }
            guard let amount = decimal(body["amount"]), amount > 0 else { return ok(["status": "ERROR", "message": "Monto inválido."]) }
            ownerReceivables[index].entries.insert(FixtureReceivable.Entry(id: nextId(), type: "payment", amount: amount, description: body["notes"] as? String ?? "",
                                                                          date: body["payment_date"] as? String ?? day(0), source: "cash_collection"), at: 0)
            return ok(["status": "OK"])
        default:
            return nil
        }
    }

    private func receivablesReport() -> [String: Any] {
        let items = ownerReceivables.map { person -> [String: Any] in
            ["id": person.id, "person_name": person.name, "current_amount_due": number(person.due), "pending_amount": number(person.due),
             "carried_pending": number(person.carried), "cycle_charges": number(person.charges), "cycle_payments": number(person.payments),
             "status": person.status, "is_auto": person.entries.contains { $0.source == "additional_card_auto" },
             "history": person.entries.map { entry -> [String: Any] in
                 ["id": entry.id, "entry_type": entry.type, "amount": number(entry.amount), "description": entry.description,
                  "entry_date": entry.date, "source_type": entry.source]
             }]
        }
        let open = ownerReceivables.filter { $0.due > 0 }
        return ["status": "OK", "cycle": ["start": "2026-09-21", "end": "2026-10-21"], "items": items,
                "summary": ["total_pending": number(open.reduce(0) { $0 + $1.due }), "count_open": open.count, "people_count": ownerReceivables.count]]
    }
}
