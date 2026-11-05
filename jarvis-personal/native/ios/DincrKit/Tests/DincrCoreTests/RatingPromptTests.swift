import Foundation
import Testing
@testable import DincrCore

struct RatingPromptTests {
    private let start = Date(timeIntervalSince1970: 1_800_000_000)
    private func later(_ days: Int) -> Date { start.addingTimeInterval(Double(days) * 86_400) }

    @Test func aNewPersonIsNotAsked() {
        #expect(!RatingPrompt.shouldAsk(firstOpen: start, saves: 50, lastAsked: nil, now: later(6)))
    }

    @Test func littleUseIsNotAsked() {
        #expect(!RatingPrompt.shouldAsk(firstOpen: start, saves: 4, lastAsked: nil, now: later(30)))
    }

    @Test func enoughUseIsAsked() {
        #expect(RatingPrompt.shouldAsk(firstOpen: start, saves: 5, lastAsked: nil, now: later(7)))
    }

    @Test func askedAgainOnlyAfterTheGap() {
        #expect(!RatingPrompt.shouldAsk(firstOpen: start, saves: 40, lastAsked: later(10), now: later(129)))
        #expect(RatingPrompt.shouldAsk(firstOpen: start, saves: 40, lastAsked: later(10), now: later(130)))
    }
}
