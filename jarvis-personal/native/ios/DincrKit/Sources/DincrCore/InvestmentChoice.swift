import Foundation

// A VIP chooses whether investing is in their plan (`GET/PUT /user-product/vip/investment-choice`):
// off until they turn it on. Android twin: `InvestmentChoice.kt`.

public struct InvestmentChoice: Codable, Sendable, Equatable {
    public let wantsInvesting: Bool
    public init(wantsInvesting: Bool) { self.wantsInvesting = wantsInvesting }
}

extension DincrService {
    public func investmentChoice() async throws -> InvestmentChoice { try await client.get("/user-product/vip/investment-choice") }

    public func updateInvestmentChoice(_ choice: InvestmentChoice) async throws -> InvestmentChoice {
        try await client.send("PUT", "/user-product/vip/investment-choice", body: choice)
    }
}
