import { NextResponse } from "next/server";
import { z } from "zod";
import { getSession } from "@/lib/auth";
import { getPortfolio } from "@/lib/db";
import { toAiHoldings } from "@/lib/portfolio";

const tradeSchema = z.object({
  ticker: z.string().trim().min(1).max(100).transform((value) => value.toUpperCase()),
  action: z.string().transform((value) => value.toUpperCase()).pipe(z.enum(["BUY", "SELL", "TRIM", "EXIT"])),
  quantity: z.coerce.number().finite().min(0.00000001),
  price: z.coerce.number().finite().positive(),
});

function unavailable(trade) {
  return NextResponse.json({
    ...trade, allowed: null, status: "unavailable", risk_level: "UNAVAILABLE",
    reasoning: "The advisory assessment is temporarily unavailable.",
  });
}

export async function POST(request) {
  try {
    const session = await getSession();
    if (!session.userId) return NextResponse.json({ error: "UNAUTHORIZED", code: "UNAUTHORIZED" }, { status: 401 });

    const body = await request.json().catch(() => null);
    const proposed = tradeSchema.safeParse(body?.proposed_trade);
    if (!proposed.success) {
      return NextResponse.json({ error: "Check the proposed trade fields.", code: "VALIDATION_ERROR" }, { status: 422 });
    }
    const proposedTrade = proposed.data;
    const { holdings } = await getPortfolio(session.userId);
    const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
    let upstream;
    try {
      upstream = await fetch(`${baseUrl}/validate-trade`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Internal-Key": process.env.INTERNAL_API_KEY || "" },
        body: JSON.stringify({ user_id: session.userId, proposed_trade: proposedTrade, portfolio: toAiHoldings(holdings) }),
        signal: AbortSignal.timeout(15000),
      });
    } catch {
      return unavailable(proposedTrade);
    }
    if (!upstream.ok) {
      if (upstream.status >= 500) return unavailable(proposedTrade);
      return NextResponse.json({ error: "Unable to validate trade.", code: "VALIDATION_FAILED" }, { status: upstream.status });
    }
    return NextResponse.json(await upstream.json());
  } catch (error) {
    console.error("Validate trade failed", error.code || error.name);
    return NextResponse.json({ error: "Internal Server Error", code: "INTERNAL_ERROR" }, { status: 500 });
  }
}
