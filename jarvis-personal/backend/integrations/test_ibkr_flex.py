from backend.integrations.ibkr_readonly import parse_flex_statement


SAMPLE_FLEX = """<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse>
  <FlexStatements count="1">
    <FlexStatement accountId="U1234567" fromDate="20260901" toDate="20260903" whenGenerated="20260903;235959">
      <AccountInformation accountId="U1234567" baseCurrency="USD" buyingPower="25.50" />
      <EquitySummaryByReportDateInBase netLiquidation="105.25" cash="5.25" />
      <OpenPositions>
        <OpenPosition symbol="VOO" assetCategory="STK" currency="USD" listingExchange="ARCA"
          position="1" costBasisPrice="90" markPrice="100" positionValue="100"
          fifoPnlUnrealized="10" />
      </OpenPositions>
      <Trades><Trade symbol="VOO" fifoPnlRealized="2.50" ibCommission="-1.00" /></Trades>
      <CashTransactions><CashTransaction type="Dividends" amount="1.25" /></CashTransactions>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>"""


def test_parse_flex_statement_maps_read_only_snapshot():
    snapshot = parse_flex_statement(SAMPLE_FLEX, account_mode="live")

    assert snapshot.account_id == "U1234567"
    assert snapshot.base_currency == "USD"
    assert snapshot.net_liquidation == 105.25
    assert snapshot.cash == 5.25
    assert snapshot.buying_power == 25.50
    assert snapshot.gross_position_value == 100
    assert snapshot.realized_pnl == 2.50
    assert snapshot.unrealized_pnl == 10
    assert snapshot.dividends == 1.25
    assert snapshot.commissions == 1
    assert snapshot.positions[0].symbol == "VOO"


def test_parse_flex_statement_falls_back_to_cash_plus_positions():
    xml = SAMPLE_FLEX.replace('netLiquidation="105.25" ', "")
    snapshot = parse_flex_statement(xml)
    assert snapshot.net_liquidation == 105.25
