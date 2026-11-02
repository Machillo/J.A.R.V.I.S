@testable import DincrCore
import Foundation
import Testing

@Suite struct OwnerNoticesTests {
    @Test func theOwnerReadsANoticeAndOnlyTheOwnerGetsOne() async throws {
        let owner = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, role: .owner, latency: .zero))
        let notices = try await owner.ownerNotices()
        #expect(notices.unread == 1)
        let notice = try #require(notices.items.first)
        #expect(notice.changed?.isEmpty == false && notice.destination?.isEmpty == false && notice.savings?.decision == "no")
        try await owner.markOwnerNoticeRead(id: notice.id)
        #expect(try await owner.ownerNotices().unread == 0)

        let user = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        await #expect(throws: APIError.self) { _ = try await user.ownerNotices() }
    }

    @Test func aNoticeWithoutOptionalFactsStillDecodes() throws {
        let json = #"{"items":[{"id":"a","title":"t","changed":"c","destination":null,"savings":null,"debt_free_date":null}],"unread":1}"#
        let notices = try APIClient.decoder.decode(OwnerNotices.self, from: Data(json.utf8))
        #expect(notices.items.first?.savings == nil && notices.items.first?.read == nil)
    }
}
