import Foundation
import Testing
@testable import DincrCore

@Suite struct MovementReviewTests {
    @Test func everydayAmountsSaveDirectly() {
        #expect(!MovementReview.isNeeded(amount: 18_450, currency: "CRC", convertsNow: false))
        #expect(!MovementReview.isNeeded(amount: Decimal(string: "499999.99")!, currency: "CRC", convertsNow: false))
        #expect(!MovementReview.isNeeded(amount: Decimal(string: "999.99")!, currency: "USD", convertsNow: false))
    }

    @Test func largeAmountsAndConversionsGetAReview() {
        #expect(MovementReview.isNeeded(amount: 500_000, currency: "CRC", convertsNow: false))
        #expect(MovementReview.isNeeded(amount: 1_000, currency: "usd", convertsNow: false))
        #expect(MovementReview.isNeeded(amount: 5, currency: "USD", convertsNow: true))
    }

    @Test func anUnknownCurrencyIsNotALargeAmount() {
        #expect(!MovementReview.isNeeded(amount: 9_000_000, currency: "EUR", convertsNow: false))
    }
}
