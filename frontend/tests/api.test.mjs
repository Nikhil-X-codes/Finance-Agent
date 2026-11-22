import assert from "node:assert/strict";
import test from "node:test";
import * as api from "../lib/api.js";
import { getSession } from "../lib/auth.js";

test("browser market-data calls go through the Next.js API", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({ ok: true }));

  await api.getPopularStocks();
  await api.searchStocks("A & B");
  await api.getStockDetail("A/B");
  await api.getFundCategories();
  await api.getFundComparison("Large Cap", true);

  assert.deepEqual(fetch.mock.calls.map(({ arguments: [path] }) => path), [
    "/api/stocks/popular", "/api/stocks/search?q=A%20%26%20B", "/api/stocks/A%2FB",
    "/api/mf/categories", "/api/mf/comparison/Large%20Cap?refresh=true",
  ]);
});

test("the browser sends only the proposed trade to the validation route", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({ allowed: true }));
  const trade = { ticker: "TCS", action: "BUY", quantity: 1, price: 100 };

  assert.deepEqual(await api.validateTrade(trade), { allowed: true });
  const [path, options] = fetch.mock.calls[0].arguments;
  assert.equal(path, "/api/trades/validate");
  assert.equal(options.method, "POST");
  assert.deepEqual(options.headers, { "Content-Type": "application/json" });
  assert.deepEqual(JSON.parse(options.body), { proposed_trade: trade });
});

test("a missing or short session secret fails closed", async () => {
  const original = process.env.SESSION_PASSWORD;
  try {
    delete process.env.SESSION_PASSWORD;
    await assert.rejects(getSession, /SESSION_PASSWORD/);
    process.env.SESSION_PASSWORD = "too-short";
    await assert.rejects(getSession, /SESSION_PASSWORD/);
  } finally {
    if (original === undefined) delete process.env.SESSION_PASSWORD;
    else process.env.SESSION_PASSWORD = original;
  }
});
