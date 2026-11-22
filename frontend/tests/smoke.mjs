import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { once } from "node:events";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const databaseUrl = process.env.SUPABASE_TEST_DB_URL;
assert.ok(databaseUrl, "Set SUPABASE_TEST_DB_URL to a disposable migrated test database.");
const require = createRequire(import.meta.url);
const serviceKey = randomUUID();
const reportId = randomUUID();
const upstream = [];
const fixtures = {
  "/health": { status: "ok" },
  "/parse-statement": {
    broker_detected: "Fixture broker", coverage_end: "2025-01-01",
    holdings: [{ ticker: "TCS", name: "TCS", quantity: 4, avg_buy_price: 100 }],
  },
  "/portfolio/risk-status": { overall_risk: "HIGH", reasoning: "Fixture risk", flags: [] },
  "/validate-trade": { allowed: true },
  "/v1/stocks/popular": { stocks: [{ symbol: "TCS" }] },
  "/v1/stocks/search": { results: [{ symbol: "TCS" }] },
  "/v1/stocks/TCS": { symbol: "TCS" },
  "/mf/categories": { categories: ["Equity"] },
  "/mf/comparison/Equity": { funds: [] },
};
const events = {
  "/generate-report": { reportId, report_json: { id: reportId, markdown: "Fixture report" } },
  "/qa": { fullText: "Fixture answer", citations: [] },
};
const backend = createServer(async (req, res) => {
  const { pathname } = new URL(req.url, "http://localhost");
  if (pathname !== "/health" && req.headers["x-internal-key"] !== serviceKey) {
    res.writeHead(403).end();
    return;
  }
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const requestBody = req.headers["content-type"] === "application/json"
    ? JSON.parse(Buffer.concat(chunks).toString()) : null;
  upstream.push({ path: pathname, body: requestBody });
  if (events[pathname]) {
    res.writeHead(200, { "Content-Type": "text/event-stream" });
    res.end(`event: complete\ndata: ${JSON.stringify(events[pathname])}\n\n`);
  } else {
    res.writeHead(fixtures[pathname] ? 200 : 404, { "Content-Type": "application/json" });
    res.end(JSON.stringify(fixtures[pathname] || {}));
  }
});

await once(backend.listen(0, "127.0.0.1"), "listening");
const reservation = createServer();
await once(reservation.listen(0, "127.0.0.1"), "listening");
const { port } = reservation.address();
await new Promise((resolve) => reservation.close(resolve));
const baseUrl = `http://127.0.0.1:${port}`;
const mode = process.argv.includes("--production") ? "start" : "dev";
const app = spawn(process.execPath, [
  require.resolve("next/dist/bin/next"), mode, "--hostname", "127.0.0.1", "--port", String(port),
], {
  cwd: fileURLToPath(new URL("../", import.meta.url)),
  windowsHide: true,
  env: {
    ...process.env,
    FASTAPI_URL: `http://127.0.0.1:${backend.address().port}`,
    SUPABASE_DB_URL: databaseUrl,
    INTERNAL_API_KEY: serviceKey,
    SESSION_PASSWORD: randomUUID(),
    NEXT_TELEMETRY_DISABLED: "1",
  },
});
let logs = "";
app.stdout.on("data", (chunk) => { logs = (logs + chunk).slice(-10000); });
app.stderr.on("data", (chunk) => { logs = (logs + chunk).slice(-10000); });

function send(path, { method = "GET", cookie, json, body, redirect = "follow" } = {}) {
  const headers = {};
  if (cookie) headers.Cookie = cookie;
  if (json) headers["Content-Type"] = "application/json";
  return fetch(baseUrl + path, {
    method, headers, body: json ? JSON.stringify(json) : body, redirect,
    signal: AbortSignal.timeout(20000),
  });
}

async function check(path, options, expected = 200) {
  const response = await send(path, options);
  if (response.status !== expected) {
    assert.fail(`${path}: expected ${expected}, got ${response.status}: ${(await response.text()).slice(0, 500)}`);
  }
  return response;
}

const post = (path, cookie, json, expected) => check(path, { method: "POST", cookie, json }, expected);
const get = (path, cookie, expected) => check(path, { cookie }, expected);
const sessionCookie = (response) => response.headers.get("set-cookie").split(";")[0];
const credentials = () => ({ email: `smoke-${randomUUID()}@example.test`, password: "synthetic-password" });

async function upload(cookie) {
  const body = new FormData();
  body.append("file", new Blob(["Ticker,Quantity\nTCS,4"], { type: "text/csv" }), "holdings.csv");
  return (await check("/api/statements/upload", { method: "POST", cookie, body })).json();
}

try {
  let ready = false;
  for (let attempt = 0; attempt < 60 && app.exitCode === null; attempt++) {
    const response = await fetch(baseUrl + "/api/health", { signal: AbortSignal.timeout(2000) }).catch(() => null);
    if (response?.ok) {
      ready = true;
      break;
    }
    await delay(1000);
  }
  assert.ok(ready, "Next.js did not become ready");
  await get("/favicon.ico");
  const signInPage = await (await get("/login")).text();
  const stylesheetPaths = [...signInPage.matchAll(/href="([^"]+\.css(?:\?[^"]*)?)"/g)]
    .map(([, path]) => path.replaceAll("&amp;", "&"));
  assert.ok(stylesheetPaths.length, "The sign-in page did not load any stylesheets");
  const css = await Promise.all([...new Set(stylesheetPaths)].map(async (path) => (await get(path)).text()));
  assert.match(css.join("\n"), /\.min-h-dvh\s*\{/, "Tailwind layout utilities were missing from the served CSS");

  for (const path of ["/api/qa", "/api/statements/upload", "/api/statements/confirm", "/api/reports/generate", "/api/trades/validate"]) {
    await post(path, null, {}, 401);
  }
  for (const path of ["/api/portfolio", "/api/stocks/popular", "/api/mf/categories"]) await get(path, null, 401);
  assert.ok(upstream.every(({ path }) => path === "/health"));

  const account = credentials();
  const { id: userId } = await (await post("/api/auth/register", null, account, 201)).json();
  const cookie = sessionCookie(await post("/api/auth/login", null, account));
  const otherCookie = sessionCookie(await post("/api/auth/register", null, credentials(), 201));
  if (process.env.SMOKE_IMPORTED_USER) {
    const imported = JSON.parse(process.env.SMOKE_IMPORTED_USER);
    const response = await post("/api/auth/login", null, { email: imported.email, password: imported.password });
    assert.equal((await response.json()).id, imported.id);
  }

  const preview = await upload(cookie);
  const confirmation = (value) => ({ previewId: value.previewId, holdings: value.holdings, coverageEnd: value.coverageEnd });
  await post("/api/statements/confirm", otherCookie, confirmation(preview), 404);
  const { snapshotId } = await (await post("/api/statements/confirm", cookie, confirmation(preview), 201)).json();
  const retried = await (await post("/api/statements/confirm", cookie, confirmation(preview), 201)).json();
  const uploadedAgain = await (await post("/api/statements/confirm", cookie, confirmation(await upload(cookie)), 201)).json();
  assert.equal(retried.snapshotId, snapshotId);
  assert.equal(uploadedAgain.snapshotId, snapshotId);

  const proposedTrade = { ticker: "TCS", action: "BUY", quantity: 1, price: 100 };
  const validation = await post("/api/trades/validate", cookie, { proposed_trade: proposedTrade, user_id: "ignored", portfolio: [] });
  assert.equal((await validation.json()).allowed, true);
  const validationCall = upstream.find(({ path }) => path === "/validate-trade");
  assert.equal(validationCall.body.user_id, userId);
  assert.equal(validationCall.body.portfolio[0].quantity, 4);

  await post("/api/trades", cookie, { ticker: "TCS", transactionType: "BUY", quantity: 1, price: 100, date: "2025-01-02" }, 201);
  const sale = { ticker: "TCS", transactionType: "SELL", quantity: 3, price: 125, date: "2025-01-03" };
  const concurrent = await Promise.all([0, 1].map(() => send("/api/trades", { method: "POST", cookie, json: sale })));
  assert.deepEqual(concurrent.map((result) => result.status).sort(), [201, 409]);
  await post("/api/trades", cookie, { ...sale, date: "2025-01-01" }, 409);
  await post("/api/trades", cookie, { ...sale, date: "2025-01-02" }, 409);
  const portfolio = await (await get("/api/portfolio", cookie)).json();
  const ledger = await (await get("/api/trades", cookie)).json();
  assert.deepEqual(ledger.trades.map((trade) => [trade.transactionType, trade.date]), [
    ["SELL", "2025-01-03"], ["BUY", "2025-01-02"],
  ]);
  assert.deepEqual((await (await get("/api/trades", otherCookie)).json()).trades, []);
  assert.equal(portfolio.holdings[0].quantity, 2);
  assert.equal(portfolio.realizedPnlTotal, 75);
  assert.equal(portfolio.marketValue, null);

  const report = await post("/api/reports/generate", cookie, { includeNews: false });
  assert.match(await report.text(), new RegExp(reportId));
  assert.equal((await (await get(`/api/reports/${reportId}`, cookie)).json()).markdown, "Fixture report");
  await get(`/api/reports/${reportId}`, otherCookie, 404);
  assert.match(await (await post("/api/qa", cookie, { question: "What do I hold?" })).text(), /Fixture answer/);
  assert.deepEqual(
    upstream.find(({ path }) => path === "/generate-report").body.portfolio,
    upstream.find(({ path }) => path === "/qa").body.portfolio_context,
  );
  const duplicateReport = await post("/api/reports/generate", cookie, { includeNews: false });
  const failedSave = await duplicateReport.text();
  assert.match(failedSave, /SAVE_FAILED/);
  assert.doesNotMatch(failedSave, /event: complete/);

  for (const path of ["/api/stocks/popular", "/api/stocks/search?q=TCS", "/api/stocks/TCS", "/api/mf/categories", "/api/mf/comparison/Equity?refresh=true"]) {
    await get(path, cookie);
  }
  const logout = await check("/api/auth/logout", { method: "POST", cookie, redirect: "manual" }, 303);
  assert.equal(new URL(logout.headers.get("location")).pathname, "/login");
  console.log("Frontend API smoke checks passed");
} catch (error) {
  console.error(logs);
  throw error;
} finally {
  if (app.exitCode === null && app.signalCode === null) {
    const stopped = once(app, "close");
    app.kill();
    await stopped;
  }
  await new Promise((resolve) => backend.close(resolve));
}
