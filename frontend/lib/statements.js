import { z } from "zod";

export const dateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine((value) => {
  const time = Date.parse(value);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
}, "Date must be a valid YYYY-MM-DD date");

export function marketDate() {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts();
  const fields = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return [fields.year, fields.month, fields.day].join("-");
}

const optionalDate = dateSchema.or(z.literal("")).nullish();
const money = z.number().finite().nonnegative();
const optionalIsin = z.string().regex(/^[A-Z]{2}[A-Z0-9]{9}\d$/).or(z.literal("")).nullish();

export const statementRowSchema = z.object({
  ticker: z.string().trim().min(1).max(100).transform((value) => value.toUpperCase()),
  isin: optionalIsin,
  name: z.string().optional().default(""),
  quantity: z.number().finite().min(0.00000001),
  avgBuyPrice: money,
  currentPrice: money.nullish(),
  sellPrice: money.nullish(),
  realizedPnl: z.number().finite().nullish(),
  buyDate: optionalDate,
  sellDate: optionalDate,
  assetType: z.enum(["STOCK", "ETF", "MUTUAL_FUND", "MF", "BOND"]).optional().default("STOCK"),
  sector: z.string().optional().default(""),
  status: z.enum(["REALIZED", "UNREALIZED"]).optional().default("UNREALIZED"),
}).superRefine((row, ctx) => {
  if (row.status === "REALIZED" && row.sellPrice == null && row.realizedPnl == null) {
    ctx.addIssue({ code: "custom", message: "Realized rows require a sale price or realized P&L." });
  }
  if (row.buyDate && row.sellDate && row.buyDate > row.sellDate) {
    ctx.addIssue({ code: "custom", message: "Purchase date must precede the sale date." });
  }
});

export const confirmSchema = z.object({
  previewId: z.string().uuid(),
  holdings: z.array(statementRowSchema).min(1).max(5000),
  coverageStart: optionalDate,
  coverageEnd: dateSchema,
}).superRefine(({ coverageStart, coverageEnd, holdings }, ctx) => {
  if (coverageEnd > marketDate() || (coverageStart && coverageStart > coverageEnd)) {
    ctx.addIssue({ code: "custom", path: ["coverageEnd"], message: "Check the statement coverage dates." });
  }
  if (holdings.some((row) => [row.buyDate, row.sellDate].some((date) => date && date > coverageEnd))) {
    ctx.addIssue({ code: "custom", path: ["coverageEnd"], message: "Statement end date precedes a transaction in this statement." });
  }
});

export function validateParsedStatement(parsed) {
  const unrecognizedRows = Array.isArray(parsed.unrecognized_rows) ? [...parsed.unrecognized_rows] : [];
  const coverageStart = dateSchema.safeParse(parsed.coverage_start);
  const coverageEnd = dateSchema.safeParse(parsed.coverage_end);
  const holdings = [];
  const tradeHistory = [];

  for (const [status, source, target] of [
    ["UNREALIZED", parsed.holdings, holdings], ["REALIZED", parsed.realized_trades, tradeHistory],
  ]) {
    if (!Array.isArray(source)) continue;
    source.forEach((raw, index) => {
      const row = raw && typeof raw === "object" ? raw : {};
      const result = statementRowSchema.safeParse({
        ticker: row.ticker || row.isin, isin: row.isin, name: row.name || row.ticker || row.isin,
        quantity: row.quantity, avgBuyPrice: row.avg_buy_price ?? row.buy_price,
        assetType: row.asset_type ?? undefined, sector: row.sector ?? undefined,
        currentPrice: row.current_price, sellPrice: row.sell_price, realizedPnl: row.realized_pnl,
        buyDate: row.buy_date, sellDate: row.sell_date, status,
      });
      if (result.success) target.push(result.data);
      else unrecognizedRows.push({ row: index + 1, section: status, values: row, reason: result.error.issues.map((issue) => issue.message).join("; ") });
    });
  }
  return {
    holdings, tradeHistory, unrecognizedRows,
    brokerDetected: parsed.broker_detected || "Unknown",
    parseConfidence: parsed.confidence ?? 0,
    summary: parsed.summary || null,
    sectorAllocation: parsed.sector_allocation || {},
    coverageStart: coverageStart.success ? coverageStart.data : null,
    coverageEnd: coverageEnd.success ? coverageEnd.data : null,
  };
}
