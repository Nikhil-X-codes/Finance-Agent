import { z } from "zod";

export const AssetTypeSchema = z.enum(["STOCK", "MUTUAL_FUND"]);
export const TransactionTypeSchema = z.enum(["BUY", "SELL"]);
export const RecommendationActionSchema = z.enum(["BUY", "HOLD", "TRIM", "EXIT"]);
export const RecommendationPrioritySchema = z.enum(["HIGH", "MEDIUM", "LOW"]);
export const ReportGeneratedViaSchema = z.enum(["LLM", "RULE_BASED"]);
export const RiskSeveritySchema = z.enum(["LOW", "MEDIUM", "HIGH"]);

const IsoDateOnlySchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

export const HoldingSchema = z.object({
  isin: z.string().length(12),
  ticker: z.string().min(1).max(20),
  name: z.string().min(1),
  quantity: z.number().positive(),
  avgBuyPrice: z.number().positive(),
  currentPrice: z.number().positive().optional(),
  sector: z.string().optional(),
  assetType: AssetTypeSchema,
});

export const TradeSchema = z.object({
  id: z.string().min(1).optional(),
  ticker: z.string().min(1).max(20),
  schemeName: z.string().min(1).optional(),
  transactionType: TransactionTypeSchema,
  quantity: z.number().positive(),
  price: z.number().positive(),
  date: z.union([IsoDateOnlySchema, z.string().datetime()]),
  createdAt: z.string().datetime().optional(),
});

export const CitationSchema = z.object({
  source: z.string().min(1),
  docTitle: z.string().min(1),
  section: z.string().min(1),
  date: z.string().datetime(),
  relevantText: z.string().min(1),
});

export const RecommendationSchema = z.object({
  ticker: z.string().min(1).max(20),
  action: RecommendationActionSchema,
  priority: RecommendationPrioritySchema,
  reasoning: z.string().min(1),
  citations: z.array(z.union([CitationSchema, z.string().min(1)])).default([]),
  disclaimer: z.string().min(1),
});

export const RiskFlagSchema = z.object({
  ticker: z.string().min(1).max(20),
  flagType: z.string().min(1),
  severity: RiskSeveritySchema,
  portfolioWeight: z.number().nonnegative().optional(),
  evidenceText: z.string().min(1),
  citation: z.string().min(1),
});

export const PortfolioSummarySchema = z.object({
  totalValue: z.number().nonnegative(),
  holdingsCount: z.number().int().nonnegative(),
  overallRiskLevel: RiskSeveritySchema,
  sectorAllocation: z.record(z.number().nonnegative()),
});

export const ReportSchema = z.object({
  id: z.string().min(1),
  createdAt: z.string().datetime(),
  generatedVia: ReportGeneratedViaSchema,
  snapshotId: z.string().min(1).optional(),
  userId: z.string().min(1).optional(),
  portfolioSummary: PortfolioSummarySchema,
  riskFlags: z.array(RiskFlagSchema).default([]),
  recommendations: z.array(RecommendationSchema),
  citations: z.array(CitationSchema).default([]),
  markdown: z.string(),
  disclaimer: z.string(),
  overallRiskLevel: RiskSeveritySchema.optional(),
});
