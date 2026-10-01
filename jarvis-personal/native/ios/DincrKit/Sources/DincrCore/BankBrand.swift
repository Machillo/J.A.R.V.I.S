import Foundation

/// Bank branding: an institution code or bank name → name, initials and logo. A port of the web
/// app's `lib/bankIdentity.js` + `lib/bankBranding.js` (same banks, codes and text patterns, same
/// order). Presentation only: it never decides data. The logos are the historical files of
/// `frontend/src/assets/institutions/` in the app's asset catalog (`logoAsset`); a bank without one
/// keeps its initials, so a missing logo never breaks a screen. Android twin: `BankBranding.kt`.
public struct BankBrand: Sendable, Equatable, Hashable {
    /// Stable id: a known bank's id (`bac`, `bn`…), or a compact form of an unknown name.
    public let id: String
    public let name: String
    public let short: String
    /// The image name in the app's asset catalog, or nil (initials).
    public let logoAsset: String?
    public let isKnown: Bool

    /// The historical MultiMoney logo is drawn in white on a transparent background: on the usual
    /// white tile it is invisible. The web app put it on a dark tile (ProfileSetup.css
    /// `.bank-mark--logo.bank-mark--violet`, #203046); the native tile does the same.
    public var logoNeedsDarkTile: Bool { logoAsset != nil && Self.whiteLogos.contains(id) }
    public static let whiteLogos: Set<String> = ["multimoney"]

    struct Identity: Sendable {
        let id: String
        let name: String
        let short: String
        let codes: [String]
        /// ICU regular expression over the plain (lowercased, accent-free) text.
        let text: String
    }

    /// Order matters for free text: "banco nacional de costa rica" must win over "banco de costa rica".
    static let identities: [Identity] = [
        Identity(id: "bac", name: "BAC Credomatic", short: "BAC", codes: ["bac", "baccredomatic", "credomatic"], text: #"\bbac\b|credomatic"#),
        Identity(id: "multimoney", name: "MultiMoney", short: "MM", codes: ["multimoney", "mm"], text: #"multi ?money"#),
        Identity(id: "bn", name: "Banco Nacional", short: "BN", codes: ["bn", "bncr", "banconacional", "banconacionaldecostarica"], text: #"banco nacional|\bbncr\b"#),
        Identity(id: "bcr", name: "Banco de Costa Rica", short: "BCR", codes: ["bcr", "bancodecostarica", "bancobcr"], text: #"banco de costa rica|\bbancobcr\b|\bbcr\b"#),
        Identity(id: "popular", name: "Banco Popular", short: "BP", codes: ["popular", "bancopopular", "bp", "bpdc"], text: #"banco popular|bancopopular"#),
        Identity(id: "davibank", name: "Davibank", short: "DB", codes: ["davibank", "scotiabank"], text: #"davibank|scotiabank"#),
        Identity(id: "davivienda", name: "Davivienda", short: "DV", codes: ["davivienda"], text: #"davivienda"#),
        Identity(id: "promerica", name: "Promerica", short: "PR", codes: ["promerica", "bancopromerica"], text: #"promerica"#),
    ]

    /// Asset catalog names (DINCR/Resources/Assets.xcassets) of the historical logos.
    public static let logoAssets: [String: String] = [
        "bac": "BankBAC", "bcr": "BankBCR", "bn": "BankBN", "davibank": "BankDavibank", "davivienda": "BankDavivienda",
        "multimoney": "BankMultiMoney", "popular": "BankPopular", "promerica": "BankPromerica",
    ]

    /// Lowercased, without accents.
    static func plain(_ value: String?) -> String {
        (value ?? "").folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX")).lowercased()
    }

    /// Only `a-z0-9`.
    static func compact(_ value: String?) -> String {
        plain(value).filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
    }

    static func matches(_ identity: Identity, text: String) -> Bool {
        text.range(of: identity.text, options: .regularExpression) != nil
    }

    static func brand(_ identity: Identity) -> BankBrand {
        BankBrand(id: identity.id, name: identity.name, short: identity.short, logoAsset: logoAssets[identity.id], isKnown: true)
    }

    /// An exact institution code or bank name (e.g. `institution_code`, `bank_name`, a candidate's
    /// `bank`), else the bank its text names. Nil when unknown.
    public static func identify(_ identifier: String?) -> BankBrand? {
        let key = compact(identifier)
        guard !key.isEmpty, key != "unknown" else { return nil }
        if let exact = identities.first(where: { $0.codes.contains(key) || compact($0.name) == key }) { return brand(exact) }
        let text = plain(identifier)
        return identities.first { matches($0, text: text) }.map(brand)
    }

    /// Free text such as an email sender or subject.
    public static func identify(inText text: String?) -> BankBrand? {
        let value = plain(text)
        guard !value.isEmpty else { return nil }
        return identities.first { matches($0, text: value) }.map(brand)
    }

    /// Always displayable: a known bank, or the institution's own name with its initials.
    public static func describe(_ identifier: String?, fallbackName: String? = nil) -> BankBrand {
        if let known = identify(identifier) ?? identify(fallbackName) { return known }
        let name = (fallbackName ?? identifier ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let id = compact(name)
        return BankBrand(id: id.isEmpty ? "unknown" : id, name: name, short: name.isEmpty ? "?" : initials(name), logoAsset: nil, isKnown: false)
    }

    /// "Banco de Ejemplo" → "E"; "Caja de Ahorro Local" → "CA" (skipping "banco", "de", "del", "la", "el").
    public static func initials(_ name: String) -> String {
        let stop: Set<String> = ["banco", "de", "del", "la", "el"]
        let cleaned = String(plain(name).map { $0.isLetter || $0.isNumber ? $0 : " " })
        let words = cleaned.split(separator: " ").map(String.init).filter { !$0.isEmpty && !stop.contains($0) }
        let value = words.count > 1 ? words.prefix(2).compactMap { $0.first }.map { String($0) }.joined() : String((words.first ?? "?").prefix(3))
        return value.uppercased()
    }

    /// The banks of the onboarding preference, with the ids `selected_financial_institutions` stores
    /// (`scotiabank` is kept for existing profiles; it shows DAVIbank's logo). `mailSupported`: the
    /// Email Monitor reads their notices (VIP).
    public static let onboardingChoices: [(id: String, mailSupported: Bool)] = [
        ("bac", true), ("bn", false), ("bcr", false), ("popular", false),
        ("davivienda", false), ("scotiabank", false), ("promerica", false), ("multimoney", true),
    ]
}
