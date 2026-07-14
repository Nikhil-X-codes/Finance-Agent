import Database from "better-sqlite3";
import path from "path";
import fs from "fs";
import crypto from "crypto";

// ---------------------------------------------------------------------------
// SQLite database initialization
// DB file lives at frontend/data/app.db — auto-created on first import.
// ---------------------------------------------------------------------------

const IS_VERCEL = !!(process.env.VERCEL || process.env.NOW_BUILDER);
const DATA_DIR = IS_VERCEL ? "/tmp" : path.join(process.cwd(), "data");

if (!IS_VERCEL && !fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

const DB_PATH = path.join(DATA_DIR, "app.db");
const db = new Database(DB_PATH);

// Enable WAL mode for better concurrent read performance
db.pragma("journal_mode = WAL");
// Enable foreign key enforcement
db.pragma("foreign_keys = ON");

// ---------------------------------------------------------------------------
// Schema — auto-migrate on first import
// ---------------------------------------------------------------------------

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    holdings_json TEXT NOT NULL,
    source TEXT DEFAULT 'STATEMENT',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS trade_log (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    ticker TEXT NOT NULL,
    transaction_type TEXT CHECK(transaction_type IN ('BUY','SELL')),
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    trade_date DATE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );

  CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    snapshot_id TEXT REFERENCES portfolio_snapshots(id),
    report_json TEXT NOT NULL,
    generated_via TEXT DEFAULT 'LLM',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );
`);

// ---------------------------------------------------------------------------
// Helper: generate a short UUID (16-char hex)
// ---------------------------------------------------------------------------
function genId() {
  return crypto.randomUUID();
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

const _insertUser = db.prepare(
  "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)"
);
const _getUserByEmail = db.prepare("SELECT * FROM users WHERE email = ?");
const _getUserById = db.prepare("SELECT id, email, created_at FROM users WHERE id = ?");

export function createUser(email, passwordHash) {
  const id = genId();
  _insertUser.run(id, email, passwordHash);
  return { id, email };
}

export function getUserByEmail(email) {
  return _getUserByEmail.get(email) || null;
}

export function getUserById(id) {
  return _getUserById.get(id) || null;
}

// ---------------------------------------------------------------------------
// Portfolio Snapshots
// ---------------------------------------------------------------------------

const _insertSnapshot = db.prepare(
  "INSERT INTO portfolio_snapshots (id, user_id, holdings_json, source) VALUES (?, ?, ?, ?)"
);
const _getSnapshotsByUser = db.prepare(
  "SELECT * FROM portfolio_snapshots WHERE user_id = ? ORDER BY created_at DESC"
);
const _getSnapshotById = db.prepare(
  "SELECT * FROM portfolio_snapshots WHERE id = ? AND user_id = ?"
);
const _getLastSnapshot = db.prepare(
  "SELECT * FROM portfolio_snapshots WHERE user_id = ? ORDER BY created_at DESC LIMIT 1"
);

export function createSnapshot(userId, holdingsJson, source = "STATEMENT") {
  const id = genId();
  _insertSnapshot.run(id, userId, JSON.stringify(holdingsJson), source);
  return { id, user_id: userId, holdings_count: holdingsJson.length, source, created_at: new Date().toISOString() };
}

export function getSnapshotsByUser(userId) {
  return _getSnapshotsByUser.all(userId).map((row) => ({
    ...row,
    holdings_json: JSON.parse(row.holdings_json),
  }));
}

export function getSnapshotById(userId, snapshotId) {
  const row = _getSnapshotById.get(snapshotId, userId);
  if (!row) return null;
  return { ...row, holdings_json: JSON.parse(row.holdings_json) };
}

export function getLastSnapshot(userId) {
  const row = _getLastSnapshot.get(userId);
  if (!row) return null;
  return { ...row, holdings_json: JSON.parse(row.holdings_json) };
}

// ---------------------------------------------------------------------------
// Trade Log
// ---------------------------------------------------------------------------

const _insertTrade = db.prepare(
  `INSERT INTO trade_log (id, user_id, ticker, transaction_type, quantity, price, trade_date)
   VALUES (?, ?, ?, ?, ?, ?, ?)`
);
const _getTradesByUser = db.prepare(
  "SELECT * FROM trade_log WHERE user_id = ? ORDER BY trade_date DESC"
);
const _getTradesSinceDate = db.prepare(
  "SELECT * FROM trade_log WHERE user_id = ? AND created_at >= ? ORDER BY trade_date ASC"
);
const _deleteTradeById = db.prepare(
  "DELETE FROM trade_log WHERE id = ? AND user_id = ?"
);
const _getTradeByIdOnly = db.prepare(
  "SELECT * FROM trade_log WHERE id = ?"
);

export function createTrade(userId, ticker, transactionType, quantity, price, tradeDate) {
  const id = genId();
  _insertTrade.run(id, userId, ticker.toUpperCase(), transactionType, quantity, price, tradeDate);
  return {
    id,
    user_id: userId,
    ticker: ticker.toUpperCase(),
    transaction_type: transactionType,
    quantity,
    price,
    trade_date: tradeDate,
    created_at: new Date().toISOString(),
  };
}

export function getTradesByUser(userId) {
  return _getTradesByUser.all(userId);
}

export function getTradesSinceDate(userId, sinceDate) {
  return _getTradesSinceDate.all(userId, sinceDate);
}

export function deleteTradeById(userId, tradeId) {
  const trade = _getTradeByIdOnly.get(tradeId);
  if (!trade) return { deleted: false, reason: "NOT_FOUND" };
  if (trade.user_id !== userId) return { deleted: false, reason: "FORBIDDEN" };
  _deleteTradeById.run(tradeId, userId);
  return { deleted: true };
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

const _insertReport = db.prepare(
  `INSERT INTO reports (id, user_id, snapshot_id, report_json, generated_via)
   VALUES (?, ?, ?, ?, ?)`
);
const _getReportsByUser = db.prepare(
  "SELECT * FROM reports WHERE user_id = ? ORDER BY created_at DESC"
);
const _getReportById = db.prepare(
  "SELECT * FROM reports WHERE id = ? AND user_id = ?"
);

export function createReport(userId, snapshotId, reportJson, generatedVia = "LLM") {
  const id = reportJson.id || genId();
  _insertReport.run(id, userId, snapshotId, JSON.stringify(reportJson), generatedVia);
  return {
    id,
    user_id: userId,
    snapshot_id: snapshotId,
    generated_via: generatedVia,
    created_at: new Date().toISOString(),
  };
}

export function getReportsByUser(userId) {
  return _getReportsByUser.all(userId).map((row) => ({
    ...row,
    report_json: JSON.parse(row.report_json),
  }));
}

export function getReportById(userId, reportId) {
  const row = _getReportById.get(reportId, userId);
  if (!row) return null;
  return { ...row, report_json: JSON.parse(row.report_json) };
}

const _updateReportJson = db.prepare(
  "UPDATE reports SET report_json = ? WHERE id = ? AND user_id = ?"
);
const _deleteReport = db.prepare(
  "DELETE FROM reports WHERE id = ? AND user_id = ?"
);

export function updateReport(userId, reportId, reportJson) {
  const result = _updateReportJson.run(JSON.stringify(reportJson), reportId, userId);
  return result.changes > 0;
}

export function deleteReport(userId, reportId) {
  const result = _deleteReport.run(reportId, userId);
  return result.changes > 0;
}

export default db;
