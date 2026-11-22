import { randomUUID } from "node:crypto";
import pg from "pg";
import { calculatePortfolio } from "./portfolio.js";

let pool;

function database() {
  if (!pool) {
    const connectionString = process.env.SUPABASE_DB_URL;
    if (!connectionString) throw new Error("Configure SUPABASE_DB_URL");
    pool = new pg.Pool({ connectionString, max: 5, connectionTimeoutMillis: 5000 });
    pool.on("error", (error) => console.error("Idle Postgres connection error", error.code || error.name));
  }
  return pool;
}

export class PortfolioConflict extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

async function first(db, sql, params) {
  return (await db.query(sql, params)).rows[0] ?? null;
}

async function transaction(run, mode = "") {
  const db = await database().connect();
  try {
    await db.query(`BEGIN ${mode}`);
    const result = await run(db);
    await db.query("COMMIT");
    return result;
  } catch (error) {
    await db.query("ROLLBACK").catch(() => {});
    throw error;
  } finally {
    db.release();
  }
}

async function lockPortfolio(db, userId) {
  const user = await first(db, "SELECT id FROM finance_agent.users WHERE id = $1 FOR UPDATE", [userId]);
  if (!user) throw new PortfolioConflict("ACCOUNT_NOT_FOUND", "Sign in again to continue.");
}

export function createUser(email, passwordHash) {
  return first(database(), `INSERT INTO finance_agent.users (id, email, password_hash)
    VALUES ($1, $2, $3) ON CONFLICT (email) DO NOTHING RETURNING id, email`, [randomUUID(), email, passwordHash]);
}

export function getUserByEmail(email) {
  return first(database(), "SELECT * FROM finance_agent.users WHERE email = $1", [email]);
}

export function getUserById(id) {
  return first(database(), "SELECT id, email, created_at FROM finance_agent.users WHERE id = $1", [id]);
}

async function latestSnapshot(db, userId) {
  return first(db, `SELECT s.id, s.holdings_json, s.created_at,
      s.coverage_start::text AS coverage_start, s.coverage_end::text AS coverage_end
    FROM finance_agent.portfolio_snapshots s WHERE s.user_id = $1
    ORDER BY s.coverage_end DESC NULLS LAST, s.created_at DESC, s.id DESC LIMIT 1`, [userId]);
}

async function portfolioTrades(db, userId, snapshot) {
  const { rows } = await db.query(`SELECT t.*, t.trade_date::text AS trade_date
    FROM finance_agent.trade_log t
    LEFT JOIN finance_agent.portfolio_snapshots s ON s.id = $2 AND s.user_id = $1
    WHERE t.user_id = $1 AND (s.id IS NULL
      OR (s.coverage_end IS NOT NULL AND t.trade_date > s.coverage_end)
      OR (s.coverage_end IS NULL AND t.created_at >= s.created_at))
    ORDER BY t.trade_date, t.created_at, t.id`, [userId, snapshot?.id ?? null]);
  return rows;
}

export function getPortfolio(userId) {
  return transaction(async (db) => {
    const snapshot = await latestSnapshot(db, userId);
    const trades = await portfolioTrades(db, userId, snapshot);
    return { snapshot, tradesMergedCount: trades.length, ...calculatePortfolio(snapshot, trades) };
  }, "ISOLATION LEVEL REPEATABLE READ READ ONLY");
}

export function createStatementPreview(userId, statementKey, parsed) {
  return first(database(), `INSERT INTO finance_agent.statement_previews (id, user_id, statement_key, parsed_json)
    VALUES ($1, $2, $3, $4) RETURNING id`, [randomUUID(), userId, statementKey, JSON.stringify(parsed)]);
}

export function confirmStatement(userId, previewId, holdings, coverageStart, coverageEnd) {
  return transaction(async (db) => {
    await lockPortfolio(db, userId);
    const preview = await first(db, `SELECT * FROM finance_agent.statement_previews
      WHERE id = $1 AND user_id = $2`, [previewId, userId]);
    if (!preview) return null;

    if (preview.snapshot_id) {
      return first(db, `SELECT id, created_at, jsonb_array_length(holdings_json) AS holdings_count
        FROM finance_agent.portfolio_snapshots WHERE id = $1 AND user_id = $2`, [preview.snapshot_id, userId]);
    }

    const previous = await latestSnapshot(db, userId);
    const { holdings: recognized, tradeHistory: realized, ...metadata } = preview.parsed_json;
    const snapshot = await first(db, `INSERT INTO finance_agent.portfolio_snapshots
      (id, user_id, holdings_json, coverage_start, coverage_end, statement_key, import_metadata)
      VALUES ($1, $2, $3, $4, $5, $6, $7)
      ON CONFLICT (user_id, statement_key) DO NOTHING
      RETURNING id, created_at, jsonb_array_length(holdings_json) AS holdings_count`, [
      randomUUID(), userId, JSON.stringify(holdings), coverageStart, coverageEnd, preview.statement_key,
      JSON.stringify({ ...metadata, recognizedCount: recognized.length, realizedCount: realized.length }),
    ]) || await first(db, `SELECT id, created_at, jsonb_array_length(holdings_json) AS holdings_count
      FROM finance_agent.portfolio_snapshots WHERE user_id = $1 AND statement_key = $2`, [userId, preview.statement_key]);
    const current = await latestSnapshot(db, userId);
    if (current.id !== previous?.id) {
      const previousTrades = await portfolioTrades(db, userId, previous);
      const currentTrades = await portfolioTrades(db, userId, current);
      const previousInvalid = new Set(calculatePortfolio(previous, previousTrades).invalidTrades);
      if (calculatePortfolio(current, currentTrades).invalidTrades.some((id) => !previousInvalid.has(id))) {
        throw new PortfolioConflict("STATEMENT_LEDGER_CONFLICT", "These holdings would leave a later sale without sufficient quantity.");
      }
    }
    await db.query(`UPDATE finance_agent.statement_previews SET snapshot_id = $1
      WHERE id = $2 AND user_id = $3`, [snapshot.id, previewId, userId]);
    return snapshot;
  });
}

function assertLedgerRemainsValid(snapshot, before, after) {
  const existing = new Set(calculatePortfolio(snapshot, before).invalidTrades);
  if (calculatePortfolio(snapshot, after).invalidTrades.some((id) => !existing.has(id))) {
    throw new PortfolioConflict("INSUFFICIENT_HOLDINGS", "This change would leave a sale without sufficient holdings on its trade date.");
  }
}

export function createTrade(userId, ticker, transactionType, quantity, price, tradeDate) {
  return transaction(async (db) => {
    await lockPortfolio(db, userId);
    const snapshot = await latestSnapshot(db, userId);
    if (snapshot?.coverage_end && tradeDate <= snapshot.coverage_end) {
      throw new PortfolioConflict("TRADE_COVERED_BY_STATEMENT", "Trade date must be after the active statement’s coverage date.");
    }
    const before = await portfolioTrades(db, userId, snapshot);
    const trade = await first(db, `INSERT INTO finance_agent.trade_log
      (id, user_id, ticker, transaction_type, quantity, price, trade_date, created_at)
      VALUES ($1, $2, $3, $4, $5, $6, $7, clock_timestamp())
      RETURNING *, trade_date::text AS trade_date`, [
      randomUUID(), userId, ticker.toUpperCase(), transactionType, quantity, price, tradeDate,
    ]);
    const after = await portfolioTrades(db, userId, snapshot);
    assertLedgerRemainsValid(snapshot, before, after);
    return trade;
  });
}

export async function getTradesByUser(userId) {
  return (await database().query(`SELECT t.id, t.ticker, t.transaction_type, t.quantity, t.price,
      t.trade_date::text AS trade_date, t.created_at
    FROM finance_agent.trade_log AS t
    WHERE t.user_id = $1 ORDER BY t.trade_date DESC, t.created_at DESC, t.id DESC`, [userId])).rows;
}

export function deleteTradeById(userId, tradeId) {
  return transaction(async (db) => {
    await lockPortfolio(db, userId);
    const snapshot = await latestSnapshot(db, userId);
    const before = await portfolioTrades(db, userId, snapshot);
    const deleted = await first(db, `DELETE FROM finance_agent.trade_log
      WHERE id = $1 AND user_id = $2 RETURNING id`, [tradeId, userId]);
    if (!deleted) return { deleted: false, reason: "NOT_FOUND" };
    assertLedgerRemainsValid(snapshot, before, before.filter((trade) => trade.id !== tradeId));
    return { deleted: true };
  });
}

export function createReport(userId, snapshotId, reportJson, generatedVia = "LLM") {
  return first(database(), `INSERT INTO finance_agent.reports (id, user_id, snapshot_id, report_json, generated_via)
    VALUES ($1, $2, $3, $4, $5) RETURNING id`,
  [reportJson.id || randomUUID(), userId, snapshotId, JSON.stringify(reportJson), generatedVia]);
}

export async function getReportsByUser(userId) {
  return (await database().query(`SELECT * FROM finance_agent.reports
    WHERE user_id = $1 ORDER BY created_at DESC, id DESC`, [userId])).rows;
}

export function getReportById(userId, reportId) {
  return first(database(), "SELECT * FROM finance_agent.reports WHERE id = $1 AND user_id = $2", [reportId, userId]);
}

export async function updateReport(userId, reportId, reportJson) {
  const { rowCount } = await database().query(`UPDATE finance_agent.reports SET report_json = $1
    WHERE id = $2 AND user_id = $3`, [JSON.stringify(reportJson), reportId, userId]);
  return rowCount > 0;
}

export async function deleteReport(userId, reportId) {
  const { rowCount } = await database().query("DELETE FROM finance_agent.reports WHERE id = $1 AND user_id = $2", [reportId, userId]);
  return rowCount > 0;
}
