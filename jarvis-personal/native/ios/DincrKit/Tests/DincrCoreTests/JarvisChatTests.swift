import Foundation
import Testing
@testable import DincrCore

/// JARVIS chat (J1): the `/jarvis/chat` contract, the tolerant reply decoder and the session's
/// conversation (sending, errors, retry, confirmation, reset). Android: `JarvisChatTest.kt`.
@Suite struct JarvisChatTests {
    // MARK: Contract

    @Test func theRequestIsTheOwnersMessage() throws {
        let body = try APIClient.encoder.encode(JarvisChatRequest(message: "Hoy hice 3 horas extra"))
        #expect(String(decoding: body, as: UTF8.self) == #"{"message":"Hoy hice 3 horas extra"}"#)
    }

    @Test func aChangeToConfirmIsRecognized() throws {
        let json = #"""
        {"message":"Voy a guardar esta evento de planilla:\n- horas: 3.0\n- monto: ₡9,000.00\n¿Confirmo y guardo? Responde sí o no.",
         "intent":"create_payroll_event","action_type":"create_payroll_event","status":"PENDING","pending":true,
         "source":"local_direct_payroll_guard","data":{"id":1,"current_field":"confirm","payload":{"hours":3.0}}}
        """#
        let reply = try APIClient.decoder.decode(JarvisChatReply.self, from: Data(json.utf8))
        #expect(reply.awaitsConfirmation && reply.pending && reply.actionType == "create_payroll_event" && reply.status == "PENDING")
    }

    @Test func aQuestionForAMissingFieldIsNotAConfirmation() throws {
        let json = #"{"message":"¿Cuál es la cuota mensual?","status":"PENDING","pending":true,"data":{"current_field":"monthly_payment"}}"#
        #expect(try !APIClient.decoder.decode(JarvisChatReply.self, from: Data(json.utf8)).awaitsConfirmation)
    }

    @Test func unexpectedShapesAroundTheMessageAreIgnored() throws {
        // `data` changes with every intent (object, list, null), `entity` can be text or an object,
        // and some answers carry extra keys: none of that may break the chat.
        for json in [
            #"{"message":"Hola","data":[1,2,3]}"#,
            #"{"message":"Hola","data":null,"entity":{"scope":"all"},"budget":null,"confidence":0.9}"#,
            #"{"message":"Hola","pending":"yes","status":7,"intent":null}"#,
            #"{"message":"Hola","pending":true,"data":{"current_field":5}}"#,
        ] {
            let reply = try APIClient.decoder.decode(JarvisChatReply.self, from: Data(json.utf8))
            #expect(reply.message == "Hola" && !reply.awaitsConfirmation, "\(json)")
        }
    }

    @Test func aClarificationIsRecognized() throws {
        let json = #"""
        {"message":"Tenés una pregunta pendiente: ¿Cómo se llama la meta? ¿\"Fondo de emergencia\" es la respuesta o querés hacer otra consulta?",
         "intent":"pending_action","action_type":"create_goal","status":"PENDING","pending":true,
         "data":{"current_field":"clarify","held_message":"Fondo de emergencia"}}
        """#
        let reply = try APIClient.decoder.decode(JarvisChatReply.self, from: Data(json.utf8))
        #expect(reply.awaitsClarification && !reply.awaitsConfirmation)
    }

    @Test func aKeptChangeStillOffersConfirmar() throws {
        // "Es otra consulta" answers the other request; the kept change (waiting for "sí") rides along.
        let json = #"{"message":"Análisis… Tenés pendiente confirmar este gasto fijo.","status":"OK","pending":true,"data":{"status":"OK"},"pending_action":{"action_type":"create_fixed_expense","current_field":"confirm"}}"#
        let reply = try APIClient.decoder.decode(JarvisChatReply.self, from: Data(json.utf8))
        #expect(reply.awaitsConfirmation && !reply.awaitsClarification)
        let question = #"{"message":"Análisis…","status":"OK","pending":true,"pending_action":{"current_field":"name"}}"#
        #expect(try !APIClient.decoder.decode(JarvisChatReply.self, from: Data(question.utf8)).awaitsConfirmation)
    }

    @Test func anAnswerWithoutAMessageIsAnError() {
        for json in [#"{}"#, #"{"message":"   "}"#, #"{"message":null,"status":"OK"}"#, #"[]"#] {
            #expect(throws: (any Error).self, "\(json)") { try APIClient.decoder.decode(JarvisChatReply.self, from: Data(json.utf8)) }
        }
    }

    // MARK: Conversation

    @MainActor @Test func aMessageShowsWhileSendingThenTheAnswer() async throws {
        let replies = ManualReplies()
        let chat = JarvisChatSession { try await replies.send($0) }
        let sending = Task { await chat.submit("  ¿Cuál es mi deuda más alta?  ") }
        try await waitUntil { await replies.waiting == 1 }
        #expect(chat.isSending)
        #expect(chat.messages.map(\.text) == ["¿Cuál es mi deuda más alta?"])
        #expect(chat.messages.first?.delivery == .sending)
        // One message at a time.
        #expect(await !chat.submit("otra pregunta"))
        await replies.answer(.success(JarvisChatReply(message: "Tu deuda más alta es la tarjeta.")))
        await sending.value
        #expect(!chat.isSending)
        #expect(chat.messages.map(\.author) == [.owner, .jarvis])
        #expect(chat.messages.map(\.delivery) == [.sent, .sent])
        #expect(await replies.sent == ["¿Cuál es mi deuda más alta?"])
        // Empty messages are never sent.
        #expect(await !chat.submit("   "))
    }

    @MainActor @Test func aFailedMessageStaysWithARetry() async throws {
        let replies = ManualReplies()
        let chat = JarvisChatSession { try await replies.send($0) }
        let first = Task { await chat.submit("Hoy hice 3 horas extra") }
        try await waitUntil { await replies.waiting == 1 }
        await replies.answer(.failure(APIError(kind: .offline, message: "Sin conexión.")))
        await first.value
        let failed = try #require(chat.messages.last)
        #expect(failed.delivery == .failed("Sin conexión.") && chat.canRetry(failed))
        #expect(chat.messages.count == 1)  // no answer was invented

        let again = Task { await chat.retry(failed.id) }
        try await waitUntil { await replies.waiting == 1 }
        #expect(chat.messages.first?.delivery == .sending)
        await replies.answer(.success(JarvisChatReply(message: "Listo.")))
        await again.value
        #expect(chat.messages.map(\.delivery) == [.sent, .sent])
        #expect(await replies.sent == ["Hoy hice 3 horas extra", "Hoy hice 3 horas extra"])
    }

    @MainActor @Test func anUnexpectedErrorStillLeavesARetry() async {
        struct Broken: Error {}
        let chat = JarvisChatSession { _ in throw Broken() }
        await chat.submit("hola")
        guard case .failed(let reason)? = chat.messages.last?.delivery else { Issue.record("not failed"); return }
        #expect(!reason.isEmpty && chat.canRetry(chat.messages[0]))
    }

    @MainActor @Test func aChangeIsSavedOnlyWithConfirmar() async throws {
        let replies = ManualReplies()
        let chat = JarvisChatSession { try await replies.send($0) }
        // Nothing is waiting: Confirmar and Cancelar send nothing.
        await chat.confirm()
        await chat.cancel()
        #expect(await replies.sent.isEmpty)

        let ask = Task { await chat.submit("Hoy hice 3 horas extra") }
        try await waitUntil { await replies.waiting == 1 }
        await replies.answer(.success(JarvisChatReply(message: "¿Confirmo y guardo?", pending: true, awaitsConfirmation: true)))
        await ask.value
        #expect(chat.awaitingConfirmation)

        let confirm = Task { await chat.confirm() }
        try await waitUntil { await replies.waiting == 1 }
        #expect(!chat.awaitingConfirmation)  // answered: the buttons go away
        await replies.answer(.success(JarvisChatReply(message: "Señor, OT registrado.")))
        await confirm.value
        #expect(await replies.sent == ["Hoy hice 3 horas extra", "sí"])
        #expect(!chat.awaitingConfirmation)
    }

    @MainActor @Test func cancelarAnswersNo() async throws {
        let replies = ManualReplies()
        let chat = JarvisChatSession { try await replies.send($0) }
        let ask = Task { await chat.submit("bono de 50 mil") }
        try await waitUntil { await replies.waiting == 1 }
        await replies.answer(.success(JarvisChatReply(message: "¿Confirmo y guardo?", pending: true, awaitsConfirmation: true)))
        await ask.value
        let cancel = Task { await chat.cancel() }
        try await waitUntil { await replies.waiting == 1 }
        await replies.answer(.success(JarvisChatReply(message: "Listo, cancelé el registro.")))
        await cancel.value
        #expect(await replies.sent.last == "no")
    }

    @MainActor @Test func aClarificationIsAnsweredWithItsTwoChoices() async throws {
        let replies = ManualReplies()
        let chat = JarvisChatSession { try await replies.send($0) }
        // Nothing is being asked: the choices send nothing.
        await chat.itIsTheAnswer()
        await chat.anotherRequest()
        #expect(await replies.sent.isEmpty)

        let ask = Task { await chat.submit("Fondo de emergencia") }
        try await waitUntil { await replies.waiting == 1 }
        await replies.answer(.success(JarvisChatReply(message: "¿Es la respuesta o querés hacer otra consulta?", pending: true, awaitsClarification: true)))
        await ask.value
        #expect(chat.awaitingClarification && !chat.awaitingConfirmation)

        let answer = Task { await chat.itIsTheAnswer() }
        try await waitUntil { await replies.waiting == 1 }
        #expect(!chat.awaitingClarification)  // answered: the choices go away
        await replies.answer(.success(JarvisChatReply(message: "¿Cuál es el monto objetivo de la meta?", pending: true)))
        await answer.value
        #expect(await replies.sent == ["Fondo de emergencia", "es la respuesta"])

        let again = Task { await chat.submit("Fondo de emergencia") }
        try await waitUntil { await replies.waiting == 1 }
        await replies.answer(.success(JarvisChatReply(message: "¿Es la respuesta?", pending: true, awaitsClarification: true)))
        await again.value
        let other = Task { await chat.anotherRequest() }
        try await waitUntil { await replies.waiting == 1 }
        await replies.answer(.success(JarvisChatReply(message: "Análisis…")))
        await other.value
        #expect(await replies.sent.last == "es otra consulta")
    }

    @MainActor @Test func resetForgetsTheConversationAndLateAnswers() async throws {
        // Sign-out or another identity: nothing of the previous conversation survives.
        let replies = ManualReplies()
        let chat = JarvisChatSession { try await replies.send($0) }
        let late = Task { await chat.submit("¿Qué tengo en la agenda?") }
        try await waitUntil { await replies.waiting == 1 }
        chat.reset()
        #expect(chat.messages.isEmpty && !chat.isSending)
        await replies.answer(.success(JarvisChatReply(message: "Tu agenda…")))
        await late.value
        #expect(chat.messages.isEmpty)
    }

    @MainActor @Test func theSessionKeepsItsLatestMessages() async {
        let chat = JarvisChatSession { JarvisChatReply(message: "respuesta a \($0)") }
        for index in 1...40 { await chat.submit("mensaje \(index)") }
        #expect(chat.messages.count == JarvisChatSession.historyLimit)
        #expect(chat.messages.last?.text == "respuesta a mensaje 40")
    }

    // MARK: Fixture backend (what the UI tests run against)

    @Test func theFixtureChatAnswersTheOwnerAndAdminOnly() async throws {
        let owner = FixtureBackend.service(FixtureBackend(role: .owner, latency: .zero))
        let change = try await owner.jarvisChat("Hoy hice 3 horas extra")
        #expect(change.awaitsConfirmation)
        #expect(try await owner.jarvisChat("sí").message.contains("registrado"))
        #expect(try await !owner.jarvisChat("¿Cuál es mi deuda más alta?").awaitsConfirmation)
        _ = try await FixtureBackend.service(FixtureBackend(role: .admin, latency: .zero)).jarvisChat("hola")

        for plan in [PlanTier.free, .basic, .vip] {
            let user = FixtureBackend.service(FixtureBackend(plan: plan, latency: .zero))
            await #expect(throws: APIError.self) { try await user.jarvisChat("hola") }
        }
        await #expect(throws: APIError.self) { try await owner.jarvisChat("respuesta rara") }

        // The scripted pending question: an ambiguous answer is asked about, "es otra consulta" keeps it.
        let goal = FixtureBackend.service(FixtureBackend(role: .owner, latency: .zero))
        #expect(try await !goal.jarvisChat("quiero crear una meta").awaitsClarification)
        #expect(try await goal.jarvisChat("Fondo de emergencia").awaitsClarification)
        #expect(try await goal.jarvisChat("es otra consulta").message.contains("Tenés una pregunta pendiente"))
        await #expect(throws: APIError.self) { try await owner.jarvisChat("falla") }
    }
}

/// A send stand-in the test answers by hand, to observe the conversation while a message is out.
private actor ManualReplies {
    private var continuations: [CheckedContinuation<JarvisChatReply, any Error>] = []
    private(set) var sent: [String] = []
    var waiting: Int { continuations.count }

    func send(_ text: String) async throws -> JarvisChatReply {
        sent.append(text)
        return try await withCheckedThrowingContinuation { continuations.append($0) }
    }

    func answer(_ result: Result<JarvisChatReply, any Error>) {
        continuations.removeFirst().resume(with: result)
    }
}

/// Main-actor isolated like the conversation tests that use it (Swift 6: the condition never crosses actors).
@MainActor
private func waitUntil(_ condition: () async -> Bool) async throws {
    for _ in 0..<1_000 {
        if await condition() { return }
        await Task.yield()
    }
    Issue.record("condition never met")
}
