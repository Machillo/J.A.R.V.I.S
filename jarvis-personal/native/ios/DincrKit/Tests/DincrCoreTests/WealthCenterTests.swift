import Foundation
import Testing
@testable import DincrCore

/// JARVIS → Patrimonio (Owner): the investment and business centers as the app reads them, and the
/// write requests. Without a portfolio snapshot the backend's 0 figures are unknown, never shown.
/// Android: `WealthCenterTest`. Synthetic data only.
struct WealthCenterTests {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try APIClient.decoder.decode(type, from: Data(json.utf8))
    }

    private func encode<T: Encodable>(_ value: T) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return String(decoding: try encoder.encode(value), as: UTF8.self)
    }

    @Test func theInvestmentCenterReadsThePortfolioAndItsPositions() throws {
        let center = try decode(InvestmentCenter.self, """
        {"portfolio":{"id":1,"market_value":1500,"contributed_capital":1350,"realized_pnl":0,"unrealized_pnl":130,"dividends":20,
                      "currency":"USD","source":"ibkr_readonly","snapshot_at":"2026-10-20T12:00:00+00:00"},
         "flows":[],"reserved_to_invest_crc":100000,"gross_pnl":150,"net_pnl":150,"return_pct":11.11,
         "positions":[{"symbol":"ETF A","sec_type":"ETF","currency":"USD","position":10,"market_price":100,"market_value":1000,"unrealized_pnl":100},
                      {"symbol":"Acción B","sec_type":"STK","currency":"USD","position":5,"market_value":500,"unrealized_pnl":30}],
         "sync_status":"current","snapshot_age_seconds":18000,"read_only":true,"sync_method":"flex","flex_configured":true,"included_in_net_worth":true}
        """)
        #expect(center.hasPortfolio)
        let figures = try #require(center.figures)
        #expect(figures.marketValue == 1_500 && figures.contributedCapital == 1_350 && figures.netPnl == 150)
        #expect(figures.returnPct == Decimal(string: "11.11") && figures.currency == "USD")
        #expect(center.positions.map(\.symbol) == ["ETF A", "Acción B"])
        #expect(center.positions[0].quantity == 10 && center.positions[1].marketPrice == nil)
        #expect(center.reservedToInvestCrc == 100_000)
        #expect(center.syncState == .current && center.ageHours == 5 && center.flexConfigured)
    }

    @Test func noSnapshotIsUnknownNotZero() throws {
        // The backend still answers 0 gains and 0 % when there is no snapshot.
        let center = try decode(InvestmentCenter.self, """
        {"portfolio":{},"flows":[],"reserved_to_invest_crc":0,"gross_pnl":0,"net_pnl":0,"return_pct":0,"positions":[],
         "sync_status":"manual_ready_for_ibkr","snapshot_age_seconds":null,"read_only":false,"sync_method":"manual","flex_configured":false}
        """)
        #expect(!center.hasPortfolio)
        #expect(center.figures == nil)
        #expect(center.syncState == .manual && center.ageHours == nil && !center.flexConfigured)
    }

    @Test func noContributedCapitalLeavesTheReturnUnknown() throws {
        let center = try decode(InvestmentCenter.self, #"{"portfolio":{"market_value":200,"contributed_capital":0},"net_pnl":0,"return_pct":0}"#)
        #expect(center.hasPortfolio && center.figures?.marketValue == 200)
        #expect(center.figures?.returnPct == nil)
    }

    @Test func theBusinessCenterReadsTheBusinessesTheirMovementsAndTotals() throws {
        let center = try decode(BusinessCenter.self, """
        {"businesses":[{"id":1,"name":"Negocio A","description":"Algo","ownership_pct":100,"status":"active"},{"id":2,"name":"Negocio B","ownership_pct":50}],
         "movements":[{"id":11,"business_id":1,"movement_date":"2026-10-12","movement_type":"income","amount":80000,"description":"Venta"},
                      {"id":12,"business_id":1,"movement_date":"2026-10-05","movement_type":"expense","amount":30000,"description":"Insumos"}],
         "income":80000,"expenses":30000,"profit":50000,"capital":0}
        """)
        #expect(center.businesses.map(\.id) == [1, 2] && center.businesses[1].ownershipPct == 50)
        #expect(center.movements(of: center.businesses[0]).map(\.id) == [11, 12])
        #expect(center.movements(of: center.businesses[1]).isEmpty)
        #expect(center.income == 80_000 && center.expenses == 30_000 && center.profit == 50_000 && center.capital == 0)
    }

    @Test func anEmptyBusinessCenterHasNoTotals() throws {
        let center = try decode(BusinessCenter.self, "{}")
        #expect(center.businesses.isEmpty && center.income == nil && center.profit == nil)
    }

    @Test func theWritesSendTheBackendsFieldNames() throws {
        #expect(try encode(BusinessCreateRequest(name: "Negocio nuevo", description: "Detalle", ownershipPct: 60))
                == #"{"description":"Detalle","name":"Negocio nuevo","ownership_pct":60}"#)
        #expect(try encode(BusinessCreateRequest(name: "Solo nombre")) == #"{"name":"Solo nombre","ownership_pct":100}"#)
        let movement = BusinessMovementRequest(businessId: 1, movementType: "expense", amount: 12_500, movementDate: "2026-10-20", description: "Insumos")
        #expect(try encode(movement) == #"{"amount":12500,"business_id":1,"description":"Insumos","movement_date":"2026-10-20","movement_type":"expense"}"#)
        #expect(movement.createsTransaction)
        #expect(!BusinessMovementRequest(businessId: 1, movementType: "capital", amount: 1, description: "Aporte").createsTransaction)
    }

    @Test func wealthIsAnAvailableJarvisSection() {
        #expect(Jarvis.Section.wealth.isAvailable)
    }
}
