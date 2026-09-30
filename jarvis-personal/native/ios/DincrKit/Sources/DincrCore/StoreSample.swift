import Foundation

/// The invented account behind the App Store screenshots (store-assets/), served by `FixtureBackend`
/// as `.store` (`-DincrFixtures store`, Debug only). It is the same account as Android's
/// `StoreSample.kt`, read from the same file: `store-sample.json` holds the account (`inputs`, written
/// by Android's StoreGoldenTest) and what the real backend engines answer for it (`engine`, written
/// and pinned by backend/tests/test_store_sample_engine.py). The fixture serves those engine answers
/// as they are — strategy, VIP command center, guided budget, Free dashboard — so a screenshot can
/// never show a figure, a priority or a sentence the backend would not produce. Nothing here is
/// hand-written advice; all names and amounts are invented.
public enum StoreSample {
    /// The fixed "today" of the sample: the second payday of September 2026.
    public static let today = "2026-09-28"

    /// `store-sample.json`, parsed once. A missing or broken resource is a build error, not a
    /// silent fallback to other sample data.
    nonisolated(unsafe) static let golden: [String: Any] = {
        guard let url = Bundle.module.url(forResource: "store-sample", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            preconditionFailure("DincrCore is missing store-sample.json")
        }
        return object
    }()

    static func entry(_ language: AppLanguage) -> [String: Any] {
        golden[language == .spanish ? "es" : "en"] as? [String: Any] ?? [:]
    }

    static func inputs(_ language: AppLanguage) -> [String: Any] { entry(language)["inputs"] as? [String: Any] ?? [:] }

    /// A backend response for this account exactly as the real engines computed it.
    static func engine(_ name: String, language: AppLanguage) -> Any {
        guard let value = (entry(language)["engine"] as? [String: Any])?[name] else {
            preconditionFailure("store-sample.json has no engine.\(name)")
        }
        return value
    }

    static func rows(_ key: String, language: AppLanguage) -> [[String: Any]] { inputs(language)[key] as? [[String: Any]] ?? [] }

    /// `/auth/me` for the sample: a first name, a plan bought in the store (not a courtesy grant).
    static func profile(plan: PlanTier, language: AppLanguage) -> [String: Any] {
        [
            "id": 4201, "email": "ana.demo@example.com", "display_name": "Ana", "role": "user",
            "plan_selected": true, "profile_setup_completed": true, "base_currency": "CRC",
            "number_format": language == .spanish ? "dot_comma" : "comma_dot", "currency_placement": "before",
            "entry_currencies": ["CRC", "USD"],
            "subscription": ["plan": plan.rawValue, "plan_name": plan.rawValue.capitalized, "status": "active", "access_source": "self_service"],
            "legal": ["required": false, "terms_version": "2026-09-23-v3", "privacy_version": "2026-09-25-v4"],
        ]
    }

    /// The declared financial situation (the engines' input).
    static func situation(_ language: AppLanguage) -> [String: Any] { inputs(language)["profile"] as? [String: Any] ?? [:] }

    /// The guided-budget limits, in the backend's row shape.
    static func budget(_ language: AppLanguage) -> [[String: Any]] {
        rows("budget_items", language: language).map { ["category": $0["category"] ?? "", "monthly_limit": $0["monthly_limit"] ?? 0] }
    }

    /// Same savings plan as Android's `StoreSample.savings()`.
    static func savings(_ language: AppLanguage) -> [[String: Any]] {
        [["id": 4, "name": language.pick("Vacaciones", "Vacation"), "monthly_amount": 25_000, "saved_amount": 75_000,
          "start_date": "2026-06-01", "end_date": "2027-06-01", "status": "active"]]
    }

    /// Same bank notices as Android's `StoreSample.candidates()`: one in colones, one in dollars that
    /// asks for the user's rate. `inputs.pending_notices` pins how many there are.
    static func candidates(_ language: AppLanguage) -> [[String: Any]] {
        let bank = language.pick("Mi banco", "My bank")
        return [
            ["candidate_id": 21, "email_id": 21, "bank": bank, "sender": "avisos@banco.example", "subject": language.pick("Notificación de compra", "Purchase notice"),
             "received_at": "2026-09-27T10:00:00Z", "description": language.pick("Supermercado", "Groceries"), "amount": 15_300, "currency": "CRC",
             "account_base_currency": "CRC", "transaction_date": "2026-09-27", "transaction_type": "expense", "category": language.pick("Comida", "Food"),
             "review_status": "pending"],
            ["candidate_id": 22, "email_id": 22, "bank": bank, "sender": "avisos@banco.example", "subject": language.pick("Compra internacional", "International purchase"),
             "received_at": "2026-09-26T10:00:00Z", "description": language.pick("Tienda en línea", "Online store"), "amount": 25, "currency": "USD",
             "account_base_currency": "CRC", "transaction_date": "2026-09-26", "transaction_type": "expense", "category": language.pick("Compras", "Shopping"),
             "review_status": "pending"],
        ]
    }
}
