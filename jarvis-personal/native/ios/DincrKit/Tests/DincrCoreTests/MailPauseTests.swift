import Foundation
import Testing
@testable import DincrCore

/// L-2: mail is paused outside the Owner. Only a mailbox or notices from before the pause still show
/// it, so they can be reviewed and disconnected (Android: `MailPauseTest.kt`).
@Suite struct MailPauseTests {
    private func status(pending: Int? = nil, connections: [String] = []) -> MailStatus {
        MailStatus(connected: nil, needsReauthorization: nil, pending: pending, microsoftAvailable: nil, consent: nil,
                   connections: connections.enumerated().map { MailStatus.Connection(id: $0.offset, provider: "gmail", googleEmail: nil, status: $0.element) })
    }

    @Test func nothingLeftMeansNoMail() {
        #expect(!status().hasLeftovers)
        #expect(!status(pending: 0).hasLeftovers)
        #expect(!status(connections: ["disabled"]).hasLeftovers, "a mailbox already disconnected is not left over")
    }

    @Test func aMailboxOrPendingNoticesAreLeftovers() {
        #expect(status(pending: 1).hasLeftovers)
        #expect(status(connections: ["active"]).hasLeftovers)
        #expect(status(connections: ["reauthorization_required"]).hasLeftovers, "an expired authorization can still be disconnected")
    }
}
