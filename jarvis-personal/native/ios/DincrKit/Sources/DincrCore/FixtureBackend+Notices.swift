import Foundation

// The fixture backend's Owner notices (Debug demos and tests only). Same shapes and access rule as
// FastAPI (`ai/owner_notices.py`): `/jarvis/*` admits only the verified Owner. Every name and amount is
// invented (CLAUDE.md §4.F).

extension FixtureBackend {
    func noticesRoute(_ method: String, _ path: String) -> Answer? {
        guard path.hasPrefix("/jarvis/premium/notices") else { return nil }
        guard profile["role"] as? String == "owner" else { return error(403, "No tienes permisos para realizar esta acción.") }
        if method == "POST" {
            ownerNoticeRead = true
            return ok(["status": "OK"])
        }
        return ok(["unread": ownerNoticeRead ? 0 : 1, "items": [[
            "id": "n1", "created_on": day(0), "read": ownerNoticeRead, "debt_id": 1,
            "title": "Bajó la cuota de Préstamo de ejemplo",
            "changed": "De ₡30.000 a ₡24.000: te liberaste ₡6.000 al mes.",
            "freed_monthly": 6000,
            "destination": "A atacar Tarjeta de ejemplo, según tu estrategia.",
            "savings": ["decision": "no", "text": "De momento no: tus deudas terminan pronto: es mejor abonarles directo."],
            "debt_free_date": "2028-03-01",
        ] as [String: Any]]])
    }
}
