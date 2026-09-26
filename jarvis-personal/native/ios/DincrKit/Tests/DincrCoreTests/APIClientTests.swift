import Foundation
import Testing
@testable import DincrCore

/// Scripted transport: returns queued responses and records every request.
final class ScriptedTransport: HTTPTransport, @unchecked Sendable {
    enum Step { case status(Int, String), failure(URLError.Code) }
    private let lock = NSLock()
    private var steps: [Step]
    private(set) var requests: [URLRequest] = []

    init(_ steps: [Step]) { self.steps = steps }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let step: Step = lock.withLock {
            requests.append(request)
            return steps.isEmpty ? .status(500, "{}") : steps.removeFirst()
        }
        switch step {
        case .failure(let code): throw URLError(code)
        case .status(let code, let body):
            return (Data(body.utf8), HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: nil, headerFields: nil)!)
        }
    }
}

final class CountingTokens: AccessTokenProvider, @unchecked Sendable {
    private let lock = NSLock()
    private(set) var refreshes = 0
    func accessToken(forceRefresh: Bool) async throws -> String {
        lock.withLock {
            if forceRefresh { refreshes += 1 }
            return "token-\(refreshes)"
        }
    }
}

@Suite struct APIClientTests {
    func client(_ transport: ScriptedTransport, tokens: CountingTokens = CountingTokens(), language: AppLanguage = .spanish) -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: tokens, transport: transport, language: language, backoff: { _ in })
    }

    @Test func sendsTheSameHeadersAsTheWebClient() async throws {
        let transport = ScriptedTransport([.status(200, #"{"status":"ok"}"#)])
        let _: Acknowledgement = try await client(transport).get("/auth/me")
        let request = try #require(transport.requests.first)
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer token-0")
        #expect(request.value(forHTTPHeaderField: "Accept-Language") == "es")
        #expect(request.value(forHTTPHeaderField: "X-Retry-Attempt") == "0")
        #expect(request.value(forHTTPHeaderField: "X-Request-ID")?.isEmpty == false)
        #expect(request.url?.absoluteString == "https://api.example.test/auth/me")
    }

    @Test func retriesSafeRequestsOnTransientStatusWithStableRequestID() async throws {
        let transport = ScriptedTransport([.status(503, "{}"), .failure(.networkConnectionLost), .status(200, "{}")])
        let _: Acknowledgement = try await client(transport).get("/user-product/free/movements")
        #expect(transport.requests.count == 3)
        let ids = Set(transport.requests.compactMap { $0.value(forHTTPHeaderField: "X-Request-ID") })
        #expect(ids.count == 1)
        #expect(transport.requests.map { $0.value(forHTTPHeaderField: "X-Retry-Attempt") } == ["0", "1", "2"])
    }

    @Test func neverRetriesWrites() async {
        let transport = ScriptedTransport([.status(503, "{}"), .status(200, "{}")])
        await #expect(throws: APIError.self) {
            let _: Acknowledgement = try await client(transport).send("POST", "/user-product/finance/expenses", body: ["amount": 1])
        }
        #expect(transport.requests.count == 1, "a write must not be sent twice")
    }

    @Test func refreshesOnceOn401ThenRepeats() async throws {
        let tokens = CountingTokens()
        let transport = ScriptedTransport([.status(401, "{}"), .status(200, "{}")])
        let _: Acknowledgement = try await client(transport, tokens: tokens).get("/auth/me")
        #expect(tokens.refreshes == 1)
        #expect(transport.requests.last?.value(forHTTPHeaderField: "Authorization") == "Bearer token-1")
    }

    @Test func secondConsecutive401IsSessionExpired() async {
        let transport = ScriptedTransport([.status(401, "{}"), .status(401, "{}")])
        do {
            let _: Acknowledgement = try await client(transport).get("/auth/me")
            Issue.record("expected failure")
        } catch let error as APIError {
            #expect(error.kind == .sessionExpired)
        } catch { Issue.record("unexpected \(error)") }
    }

    @Test func spanishDetailIsShownOnlyToSpanishSessions() async {
        let body = #"{"detail":"El periodo debe tener formato YYYY-MM."}"#
        for (language, expected) in [(AppLanguage.spanish, "El periodo debe tener formato YYYY-MM."), (.english, "Check the information and try again.")] {
            let transport = ScriptedTransport([.status(422, body)])
            do {
                let _: Acknowledgement = try await client(transport, language: language).get("/x")
            } catch let error as APIError {
                #expect(error.kind == .validation)
                #expect(error.message == expected)
            } catch { Issue.record("unexpected \(error)") }
        }
    }

    @Test func accountDeletionPendingCarriesItsCode() async {
        let body = #"{"detail":{"code":"account_deletion_pending","message":"Tu cuenta se está eliminando."}}"#
        let transport = ScriptedTransport([.status(409, body)])
        do {
            let _: Acknowledgement = try await client(transport, language: .english).get("/auth/me")
        } catch let error as APIError {
            #expect(error.code == "account_deletion_pending")
            #expect(error.message == "Tu cuenta se está eliminando.")
        } catch { Issue.record("unexpected \(error)") }
    }

    @Test func offlineAfterRetriesIsReportedAsOffline() async {
        let transport = ScriptedTransport([.failure(.notConnectedToInternet), .failure(.notConnectedToInternet), .failure(.notConnectedToInternet)])
        do {
            let _: Acknowledgement = try await client(transport).get("/auth/me")
        } catch let error as APIError {
            #expect(error.kind == .offline)
            #expect(error.isTransient)
        } catch { Issue.record("unexpected \(error)") }
    }
}
