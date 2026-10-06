import Foundation
import Testing
@testable import DincrCore

/// UX-6 (UNKNOWN ≠ 0): the command center sends null for figures it can't compute, a director
/// priority "incomplete", an empty roadmap and `missing` codes. The app reads them as unknown
/// ("—", no section), never as ₡0. Android: `CommandCenterUnknownTest.kt`. Synthetic data.
@Suite struct CommandCenterUnknownTests {
    private let json = #"""
    {"director":{"priority":"incomplete","headline":"Aún no tengo suficiente información para recomendarte una prioridad",
                 "next_action":"Completá la información que falta para que DINCR pueda recomendarte.","data_complete":false,
                 "missing":["income"]},
     "safe_to_spend":{"amount":null,"monthly_margin":null,"next_45_days_minimum":250000.0,"missing":["income"]},
     "roadmap":[],"alerts":[],"automation":{"review":0}}
    """#

    @Test func unknownFiguresDecodeAsUnknownNeverZero() throws {
        let center = try APIClient.decoder.decode(CommandCenter.self, from: Data(json.utf8))
        #expect(center.safeToSpend?.amount == nil)
        #expect(center.safeToSpend?.monthlyMargin == nil)
        #expect(center.safeToSpend?.next45DaysMinimum == Decimal(250000))
        #expect(center.director?.priority == "incomplete")
        #expect(center.director?.headline?.isEmpty == false)  // Hoy shows the backend's sentence, not the code
        #expect(center.roadmap?.isEmpty ?? true)              // no roadmap section
        #expect(AttentionList.today(center: center).isEmpty)  // nothing invented for "Para atender"
    }
}
