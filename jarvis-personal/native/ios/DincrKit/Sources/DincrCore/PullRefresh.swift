import Foundation

/// B17 — pull to refresh on Plan, Patrimonio and Perfil (Hoy and Movimientos keep their own). A tab
/// reads again only what it already reads: the identity (plan and role, `/auth/me`), the operational
/// switches and, in Patrimonio, the debts. A failed refresh never empties a screen: it keeps what it
/// showed and says so apart (`failureNotice`).
public enum PullRefresh {
    /// What a screen shows after a refresh: the new answer, or what it already showed when the
    /// refresh failed. Nil only when there was nothing to keep (the screen shows its own error).
    public static func kept<Value>(_ current: Value?, after result: Result<Value, any Error>) -> Value? {
        switch result {
        case .success(let value): value
        case .failure: current
        }
    }

    public static func failureNotice(_ language: AppLanguage = .current) -> String {
        language.pick("No pudimos actualizar. Seguís viendo la información anterior.",
                      "We couldn’t refresh. You’re still seeing the previous information.")
    }
}

/// One refresh at a time: a refresh asked for while another is running (a second pull, here or on
/// another tab) waits for that one and gets its result instead of asking again.
@MainActor
public final class SingleFlight {
    private var running: Task<Bool, Never>?

    public init() {}

    public var isRunning: Bool { running != nil }

    public func run(_ work: @escaping @MainActor () async -> Bool) async -> Bool {
        if let running { return await running.value }
        let task = Task { await work() }
        running = task
        let result = await task.value
        running = nil
        return result
    }
}
