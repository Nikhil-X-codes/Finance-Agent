import { NextResponse } from "next/server";
import { z } from "zod";
import { getSession } from "@/lib/auth";
import { createSnapshot } from "@/lib/db";

const holdingSchema = z.object({
  isin: z.string().regex(/^[A-Z]{2}[A-Z0-9]{9}\d$/, "Invalid ISIN format").optional().or(z.literal("")),
  ticker: z.string().min(1),
  name: z.string().optional().default(""),
  quantity: z.number().nonnegative(),
  avgBuyPrice: z.number().nonnegative(),
  assetType: z.enum(["STOCK", "MF", "MUTUAL_FUND", "ETF", "BOND"]).optional().default("STOCK"),
  sector: z.string().optional().default(""),
  status: z.string().optional().default("UNREALIZED"),
  currentPrice: z.number().optional().nullable(),
  sellPrice: z.number().optional().nullable(),
  realizedPnl: z.number().optional().nullable(),
  buyDate: z.string().optional().nullable(),
  sellDate: z.string().optional().nullable(),
});

const confirmSchema = z.object({
  previewId: z.string().min(1),
  holdings: z.array(holdingSchema).min(1, "At least one holding is required"),
});

export async function POST(request) {
  try {
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const body = await request.json();
    const parsed = confirmSchema.safeParse(body);

    if (!parsed.success) {
      return NextResponse.json(
        { error: "VALIDATION_ERROR", details: parsed.error.flatten().fieldErrors },
        { status: 422 }
      );
    }

    const { holdings } = parsed.data;

    // Save confirmed holdings as a portfolio snapshot
    const snapshot = createSnapshot(session.userId, holdings, "STATEMENT");

    return NextResponse.json(
      {
        snapshotId: snapshot.id,
        holdingsCount: holdings.length,
        createdAt: snapshot.created_at,
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("Confirm error:", error);
    return NextResponse.json(
      { error: "Confirmation failed", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
