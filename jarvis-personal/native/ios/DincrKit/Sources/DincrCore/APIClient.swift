import Foundation

/// Supplies the bearer token for API calls. `forceRefresh` is used once after a 401.
public protocol AccessTokenProvider: Sendable {
    func accessToken(forceRefresh: Bool) async throws -> String
}

/// Abstracts the network so tests can script responses.
public protocol HTTPTransport: Sendable {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

public struct URLSessionTransport: HTTPTransport {
    let session: URLSession
    public init(session: URLSession = .shared) { self.session = session }

    public func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        return (data, http)
    }
}

/// DINCR API client. Same contract as `frontend/src/lib/authenticatedFetch.js`:
/// - `Authorization: Bearer`, `Accept-Language`, `X-Request-ID` (stable across retries),
///   `X-Retry-Attempt`;
/// - safe methods (GET/HEAD) retry up to 2 times on 408, 425, 429, 502, 503, 504 and on
///   network loss; writes are never retried automatically, and creates carry an
///   `X-Idempotency-Key` so a repeated submit is answered from the first one;
/// - a 401 refreshes the session once and repeats the request;
/// - 20 s timeout per attempt.
public struct APIClient: Sendable {
    public static let retryableStatus: Set<Int> = [408, 425, 429, 502, 503, 504]

    let baseURL: URL
    let tokens: AccessTokenProvider
    let transport: HTTPTransport
    let language: AppLanguage
    let timeout: TimeInterval
    let backoff: @Sendable (Int) async -> Void

    public init(
        baseURL: URL, tokens: AccessTokenProvider, transport: HTTPTransport = URLSessionTransport(),
        language: AppLanguage = .current, timeout: TimeInterval = 20,
        backoff: @escaping @Sendable (Int) async -> Void = { attempt in
            try? await Task.sleep(for: .milliseconds(400 * (1 << attempt)))
        }
    ) {
        self.baseURL = baseURL; self.tokens = tokens; self.transport = transport
        self.language = language; self.timeout = timeout; self.backoff = backoff
    }

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    public func get<Response: Decodable>(_ path: String, query: [URLQueryItem] = [], as type: Response.Type = Response.self) async throws -> Response {
        try await perform(method: "GET", path: path, query: query, body: nil)
    }

    public func send<Body: Encodable, Response: Decodable>(_ method: String, _ path: String, body: Body, idempotencyKey: String? = nil, as type: Response.Type = Response.self) async throws -> Response {
        let data: Data
        do { data = try Self.encoder.encode(body) } catch { throw APIError.decoding(language) }
        return try await perform(method: method, path: path, query: [], body: data, idempotencyKey: idempotencyKey)
    }

    public func send<Response: Decodable>(_ method: String, _ path: String, as type: Response.Type = Response.self) async throws -> Response {
        try await perform(method: method, path: path, query: [], body: nil)
    }

    func perform<Response: Decodable>(method: String, path: String, query: [URLQueryItem], body: Data?, idempotencyKey: String? = nil) async throws -> Response {
        let requestID = UUID().uuidString.lowercased()
        let safe = method == "GET" || method == "HEAD"
        let maxRetries = safe ? 2 : 0
        var attempt = 0
        var refreshed = false
        var token = try await tokens.accessToken(forceRefresh: false)

        while true {
            var request = URLRequest(url: url(path, query: query), timeoutInterval: timeout)
            request.httpMethod = method
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
            request.setValue(language.rawValue, forHTTPHeaderField: "Accept-Language")
            request.setValue(requestID, forHTTPHeaderField: "X-Request-ID")
            request.setValue(String(attempt), forHTTPHeaderField: "X-Retry-Attempt")
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            if let idempotencyKey { request.setValue(idempotencyKey, forHTTPHeaderField: "X-Idempotency-Key") }

            let data: Data
            let response: HTTPURLResponse
            do {
                (data, response) = try await transport.send(request)
            } catch let error as URLError {
                // A cancelled task (the screen went away) is not an outage: never show "offline".
                if error.code == .cancelled { throw CancellationError() }
                if attempt < maxRetries, Self.isTransient(error) {
                    await backoff(attempt); attempt += 1; continue
                }
                throw error.code == .timedOut ? APIError.timeout(language) : APIError.offline(language)
            }

            if response.statusCode == 401, !refreshed {
                refreshed = true
                token = try await tokens.accessToken(forceRefresh: true)
                continue
            }
            if Self.retryableStatus.contains(response.statusCode), attempt < maxRetries {
                await backoff(attempt); attempt += 1; continue
            }
            guard (200..<300).contains(response.statusCode) else {
                throw APIError.from(status: response.statusCode, body: data, language: language, requestID: requestID)
            }
            do {
                return try Self.decoder.decode(Response.self, from: data.isEmpty ? Data("{}".utf8) : data)
            } catch {
                throw APIError.decoding(language)
            }
        }
    }

    func url(_ path: String, query: [URLQueryItem]) -> URL {
        var components = URLComponents(url: baseURL.appending(path: path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query }
        return components.url!
    }

    static func isTransient(_ error: URLError) -> Bool {
        [.notConnectedToInternet, .networkConnectionLost, .timedOut, .cannotConnectToHost, .dnsLookupFailed].contains(error.code)
    }
}
