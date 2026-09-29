import Foundation

/// Plans the public app serves. The backend is authoritative (`require_feature` answers 402/403);
/// this only decides what the app offers, with the same minimums as `auth/saas.py`
/// `BUILTIN_FEATURE_MIN_PLAN`, so a screen is never shown to a plan the server would refuse.
/// Same table as Android `Plans.kt`.
public enum PlanTier: String, Sendable, CaseIterable, Comparable {
    case free, basic, vip

    public var rank: Int {
        switch self {
        case .free: 0
        case .basic: 1
        case .vip: 2
        }
    }

    public func allows(_ feature: Feature) -> Bool { rank >= feature.minimum.rank }

    /// Unknown or missing plan codes are Free: the app never offers more than the server grants.
    public static func from(_ wire: String?) -> PlanTier { PlanTier(rawValue: wire?.lowercased() ?? "") ?? .free }

    public static func < (lhs: PlanTier, rhs: PlanTier) -> Bool { lhs.rank < rhs.rank }
}

public enum Feature: String, Sendable, CaseIterable {
    case financeOverview, spending, debts, goals, transactions
    /// Also edits of debts and goals (`PUT /finance/debts/{id}`, `PUT /goals/{id}`).
    case strategyBasic, basicDashboard, guidedBudget, financialCalendar, recurringItems, basicReports
    case strategyVip, gmailAutomation

    public var minimum: PlanTier {
        switch self {
        case .financeOverview, .spending, .debts, .goals, .transactions: .free
        case .strategyBasic, .basicDashboard, .guidedBudget, .financialCalendar, .recurringItems, .basicReports: .basic
        case .strategyVip, .gmailAutomation: .vip
        }
    }
}

/// Operational kill switches (`GET /product-ops/feature-flags`). Unknown means the backend's safe
/// default: writes, mail and store purchases paused; VIP intelligence and reports on.
public enum OpsFlag: String, Sendable, CaseIterable {
    case financialWrites = "financial_writes"
    case gmailAutomation = "gmail_automation"
    case vipIntelligence = "vip_intelligence"
    case advancedReports = "advanced_reports"
    case storeBilling = "store_billing"

    public var safeDefault: Bool {
        switch self {
        case .financialWrites, .gmailAutomation, .storeBilling: false
        case .vipIntelligence, .advancedReports: true
        }
    }
}

/// Local app lock (Face ID / Touch ID or the device passcode). It locks at launch and after five
/// minutes in the background, like the Capacitor app.
public enum AppLockPolicy {
    public static let timeout: TimeInterval = 5 * 60

    public static func shouldLock(enabled: Bool, backgroundedAt: TimeInterval?, now: TimeInterval) -> Bool {
        guard enabled, let backgroundedAt else { return false }
        return now - backgroundedAt >= timeout
    }
}
