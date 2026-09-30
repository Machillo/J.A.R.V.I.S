import Foundation
import Observation

/// Body of `POST /jarvis/chat` (Owner): one message, in the Owner's own words.
public struct JarvisChatRequest: Encodable, Sendable, Equatable {
    public let message: String
    public init(message: String) { self.message = message }
}

/// The JARVIS engine's answer to one message (`backend/ai/jarvis_engine.process_message`).
///
/// The backend sends an untyped dict whose `data` changes with every intent: only `message` is
/// required, the rest is read defensively and anything else is ignored. A change the chat
/// understood (a payroll event, a bonus, an event, a memory, a fixed expense…) comes back with
/// `pending: true` and `data.current_field == "confirm"`: it is saved only if the Owner answers
/// "sí" (`awaitsConfirmation`). Android twin: `JarvisChat.kt`.
public struct JarvisChatReply: Decodable, Sendable, Equatable {
    public let message: String
    public let intent: String?
    public let status: String?
    public let pending: Bool
    public let actionType: String?
    /// JARVIS showed what it will save and waits for "sí" / "no".
    public let awaitsConfirmation: Bool

    public init(message: String, intent: String? = nil, status: String? = nil, pending: Bool = false,
                actionType: String? = nil, awaitsConfirmation: Bool = false) {
        self.message = message; self.intent = intent; self.status = status; self.pending = pending
        self.actionType = actionType; self.awaitsConfirmation = awaitsConfirmation
    }

    enum CodingKeys: String, CodingKey { case message, intent, status, pending, actionType, data }
    enum DataKeys: String, CodingKey { case currentField }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let text = try? container.decodeIfPresent(String.self, forKey: .message)
        guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw DecodingError.dataCorrupted(.init(codingPath: [CodingKeys.message], debugDescription: "JARVIS answered without a message"))
        }
        message = text
        intent = try? container.decodeIfPresent(String.self, forKey: .intent)
        status = try? container.decodeIfPresent(String.self, forKey: .status)
        pending = (try? container.decodeIfPresent(Bool.self, forKey: .pending)) ?? false
        actionType = try? container.decodeIfPresent(String.self, forKey: .actionType)
        let data = try? container.nestedContainer(keyedBy: DataKeys.self, forKey: .data)
        let field = data.flatMap { try? $0.decodeIfPresent(String.self, forKey: .currentField) }
        awaitsConfirmation = pending && field == "confirm"
    }
}

/// One JARVIS conversation, kept only for the signed-in session: nothing is stored on the device
/// or the server (the web Owner app kept its chat the same way). Messages go out one at a time,
/// in order; a message that could not be sent stays in the list with a retry.
@MainActor
@Observable
public final class JarvisChatSession {
    public struct Message: Identifiable, Equatable, Sendable {
        public enum Author: Sendable, Equatable { case owner, jarvis }
        public enum Delivery: Sendable, Equatable { case sending, sent, failed(String) }

        public let id: Int
        public let author: Author
        public let text: String
        public var delivery: Delivery
        /// For a JARVIS message: it shows a change and waits for "sí" / "no".
        public var awaitsConfirmation: Bool
    }

    /// The answers to a pending change (backend `action_flow.YES_WORDS` / `NO_WORDS`).
    public static let confirmWord = "sí"
    public static let cancelWord = "no"
    /// The oldest messages leave the list past this many (the session only).
    public static let historyLimit = 60

    public private(set) var messages: [Message] = []
    public private(set) var isSending = false

    private let send: @Sendable (String) async throws -> JarvisChatReply
    private var nextID = 1
    /// Bumped by `reset()`: an answer to an earlier session is dropped.
    private var generation = 0

    public init(send: @escaping @Sendable (String) async throws -> JarvisChatReply) {
        self.send = send
    }

    /// JARVIS's last message waits for "sí" / "no" and nothing is on its way.
    public var awaitingConfirmation: Bool {
        !isSending && messages.last?.author == .jarvis && messages.last?.awaitsConfirmation == true
    }

    /// Whether a failed message can be sent again (only the latest one: messages stay in order).
    public func canRetry(_ message: Message) -> Bool {
        guard !isSending, case .failed = message.delivery else { return false }
        return messages.last?.id == message.id
    }

    /// Sends one message; empty text, or a message while another is on its way, is ignored.
    @discardableResult
    public func submit(_ text: String) async -> Bool {
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !isSending else { return false }
        let id = append(.owner, clean, delivery: .sending)
        await deliver(id, clean)
        return true
    }

    public func confirm() async { if awaitingConfirmation { await submit(Self.confirmWord) } }
    public func cancel() async { if awaitingConfirmation { await submit(Self.cancelWord) } }

    public func retry(_ id: Int) async {
        guard let message = messages.first(where: { $0.id == id }), canRetry(message) else { return }
        update(id) { $0.delivery = .sending }
        await deliver(id, message.text)
    }

    /// Sign-out or another identity: the conversation is gone.
    public func reset() {
        generation += 1
        messages = []
        isSending = false
    }

    private func deliver(_ id: Int, _ text: String) async {
        let session = generation
        isSending = true
        // Any question JARVIS asked is answered (or set aside) by this message.
        for index in messages.indices where messages[index].awaitsConfirmation { messages[index].awaitsConfirmation = false }
        let outcome: Result<JarvisChatReply, Error>
        do { outcome = .success(try await send(text)) } catch { outcome = .failure(error) }
        guard session == generation else { return }
        isSending = false
        switch outcome {
        case .success(let reply):
            update(id) { $0.delivery = .sent }
            append(.jarvis, reply.message, delivery: .sent, awaitsConfirmation: reply.awaitsConfirmation)
        case .failure(let error):
            let text = (error as? APIError)?.message
                ?? AppLanguage.current.pick("No pudimos enviar el mensaje. Intentá de nuevo.", "We couldn’t send the message. Please try again.")
            update(id) { $0.delivery = .failed(text) }
        }
    }

    @discardableResult
    private func append(_ author: Message.Author, _ text: String, delivery: Message.Delivery, awaitsConfirmation: Bool = false) -> Int {
        let id = nextID
        nextID += 1
        messages.append(Message(id: id, author: author, text: text, delivery: delivery, awaitsConfirmation: awaitsConfirmation))
        if messages.count > Self.historyLimit { messages.removeFirst(messages.count - Self.historyLimit) }
        return id
    }

    private func update(_ id: Int, _ change: (inout Message) -> Void) {
        guard let index = messages.firstIndex(where: { $0.id == id }) else { return }
        change(&messages[index])
    }
}
