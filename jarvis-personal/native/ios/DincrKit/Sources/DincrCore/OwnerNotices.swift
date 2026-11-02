import Foundation

/// `GET /jarvis/premium/notices` (Owner): what changed in his money and what it means today. Every
/// figure and sentence comes from the backend (`ai/owner_notices.py`); nothing here computes money.
public struct OwnerNotices: Decodable, Sendable, Equatable {
    public struct Savings: Decodable, Sendable, Equatable {
        /// `yes`, `partial`, `no` or `unknown`.
        public let decision: String?
        public let text: String?
    }

    public struct Notice: Decodable, Sendable, Equatable, Identifiable {
        public let id: String
        public let createdOn: String?
        public let read: Bool?
        public let title: String?
        public let changed: String?
        public let destination: String?
        public let savings: Savings?
        public let debtFreeDate: String?
    }

    public let items: [Notice]
    public let unread: Int?
}

public extension DincrService {
    func ownerNotices() async throws -> OwnerNotices { try await client.get("/jarvis/premium/notices") }

    func markOwnerNoticeRead(id: String) async throws {
        let _: Acknowledgement = try await client.send("POST", "/jarvis/premium/notices/\(id)/read")
    }
}
