import Foundation
import Testing
@testable import DincrCore

/// B17 — pull to refresh on Plan, Patrimonio and Perfil: a failed refresh keeps what the screen
/// showed, one refresh runs at a time, and the fixture used by the UI tests fails only the identity
/// read again. Android: `PullRefreshTest.kt`. Synthetic data.
@Suite struct PullRefreshTests {
    private struct Unreachable: Error {}

    @Test func aSuccessfulRefreshShowsTheNewAnswer() {
        #expect(PullRefresh.kept([1, 2], after: .success([3])) == [3])
        #expect(PullRefresh.kept(nil, after: .success([3])) == [3])
    }

    @Test func aFailedRefreshKeepsWhatTheScreenShowed() {
        #expect(PullRefresh.kept([1, 2], after: .failure(Unreachable())) == [1, 2])
    }

    @Test func aFailedFirstReadHasNothingToKeep() {
        #expect(PullRefresh.kept([Int]?.none, after: .failure(Unreachable())) == nil)
    }

    @Test func theFailureNoticeIsTheSameOnBothPlatforms() {
        #expect(PullRefresh.failureNotice(.spanish) == "No pudimos actualizar. Seguís viendo la información anterior.")
        #expect(PullRefresh.failureNotice(.english) == "We couldn’t refresh. You’re still seeing the previous information.")
    }

    @MainActor private final class Calls { var count = 0 }

    @MainActor @Test func aSecondRefreshWhileOneRunsJoinsItInsteadOfAskingAgain() async {
        let flight = SingleFlight()
        let calls = Calls()
        let (gate, open) = AsyncStream<Void>.makeStream()
        let first = Task { @MainActor in
            await flight.run {
                calls.count += 1
                for await _ in gate { break }
                return true
            }
        }
        while !flight.isRunning { await Task.yield() }
        let second = Task { @MainActor in
            await flight.run { calls.count += 1; return false }
        }
        for _ in 0..<20 { await Task.yield() }
        open.yield(())
        #expect(await first.value)
        #expect(await second.value, "the second pull gets the running refresh's result")
        #expect(calls.count == 1, "one read, not two")
        #expect(!flight.isRunning)
    }

    @MainActor @Test func aRefreshAfterTheLastOneEndedReadsAgain() async {
        let flight = SingleFlight()
        let calls = Calls()
        #expect(await flight.run { calls.count += 1; return false } == false)
        #expect(await flight.run { calls.count += 1; return true })
        #expect(calls.count == 2)
    }

    @Test func theFixtureFailsOnlyWhatAPullReadsAgain() async throws {
        let failing = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero, identityRefreshFails: true))
        _ = try await failing.me()
        do {
            _ = try await failing.me()
            Issue.record("the second identity read should fail")
        } catch let error as APIError {
            #expect(error.isTransient, "like an unreachable server: the app keeps the user where they were")
        }
        _ = try await failing.debts()
        _ = try await failing.debts()  // not a refreshed source: never fails
        // NAT-03: Hoy's main source and the movement list, read again.
        _ = try await failing.freeDashboard()
        _ = try await failing.movements()
        for read in [{ _ = try await failing.freeDashboard() }, { _ = try await failing.movements() }] as [() async throws -> Void] {
            do {
                try await read()
                Issue.record("a second read of a refreshed source should fail")
            } catch let error as APIError {
                #expect(error.isTransient)
            }
        }

        let normal = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        _ = try await normal.me()
        _ = try await normal.me()
    }
}
