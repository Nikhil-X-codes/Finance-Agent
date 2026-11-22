import assert from "node:assert/strict";
import test from "node:test";
import { calculatePortfolio, toAiHoldings } from "../lib/portfolio.js";
import { confirmSchema, validateParsedStatement } from "../lib/statements.js";

const holding = { ticker: "TCS", quantity: 10, avgBuyPrice: 100, currentPrice: 120 };
const sale = { id: "sale", ticker: "TCS", transaction_type: "SELL", quantity: 4, price: 130, trade_date: "2025-04-02" };

test("partial sales realize P&L and preserve remaining cost basis", () => {
  const portfolio = calculatePortfolio({ holdings_json: [holding], coverage_end: "2025-04-01" }, [sale]);
  assert.equal(portfolio.holdings[0].quantity, 6);
  assert.equal(portfolio.investedCost, 600);
  assert.equal(portfolio.marketValue, 720);
  assert.equal(portfolio.realizedPnlTotal, 120);
  assert.equal(portfolio.unrealizedPnl, 120);
  assert.equal(toAiHoldings(portfolio.holdings)[0].price_as_of, "2025-04-01");
});

test("closed and reopened positions retain realized history and have no inferred price", () => {
  const trades = [
    { ...sale, quantity: 10 },
    { ...sale, id: "reopen", transaction_type: "BUY", quantity: 2, price: 125 },
  ];
  const portfolio = calculatePortfolio({ holdings_json: [holding] }, trades);
  assert.equal(portfolio.realizedPnlTotal, 300);
  assert.equal(portfolio.investedCost, 250);
  assert.equal(portfolio.marketValue, null);
  assert.equal(portfolio.unrealizedPnl, null);
  assert.equal(toAiHoldings(portfolio.holdings)[0].current_price, null);
});

test("legacy oversells are surfaced and do not create inventory or gains", () => {
  const result = calculatePortfolio({ holdings_json: [holding] }, [{ ...sale, quantity: 11 }]);
  assert.deepEqual(result.invalidTrades, ["sale"]);
  assert.equal(result.holdings[0].quantity, 10);
  assert.equal(result.realizedPnlTotal, 0);
});

test("merges multiple lots and accepts sale by a known ISIN alias", () => {
  const isin = "INE467B01029";
  const snapshot = {
    holdings_json: [{ ...holding, isin }, { ...holding, ticker: isin, isin, quantity: 2, avgBuyPrice: 130 }],
  };
  const portfolio = calculatePortfolio(snapshot, [{ ...sale, ticker: isin }]);
  assert.equal(portfolio.holdings[0].ticker, "TCS");
  assert.equal(portfolio.holdings[0].quantity, 8);
  assert.equal(portfolio.holdings[0].avgBuyPrice, 105);
  assert.equal(portfolio.realizedPnlTotal, 100);
});

test("statement preview rejects incomplete rows and preserves missing quote and explicit coverage", () => {
  const result = validateParsedStatement({
    holdings: [
      { ticker: "TCS", quantity: 2, avg_buy_price: 100, current_price: null },
      { ticker: "INFY", quantity: 1 },
    ],
    coverage_end: "2025-04-01",
  });
  assert.equal(result.holdings.length, 1);
  assert.equal(result.holdings[0].currentPrice, null);
  assert.equal(result.unrecognizedRows.length, 1);
  const input = { previewId: "c460367a-b085-41d4-8acb-f0b3e335c558", holdings: result.holdings };
  assert.equal(confirmSchema.safeParse({ ...input, coverageEnd: result.coverageEnd }).success, true);
  assert.equal(confirmSchema.safeParse({ ...input, coverageEnd: "2025-02-30" }).success, false);
});
