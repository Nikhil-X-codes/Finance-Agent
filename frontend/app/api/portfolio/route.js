import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getPortfolio } from "@/lib/db";
import { toAiHoldings } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const session = await getSession();
    if (!session.userId) return NextResponse.json({ error: "UNAUTHORIZED", code: "UNAUTHORIZED" }, { status: 401 });

    const { snapshot, ...portfolio } = await getPortfolio(session.userId);
    if (!snapshot && !portfolio.tradesMergedCount) {
      return NextResponse.json({ error: "No portfolio found.", code: "NO_PORTFOLIO" }, { status: 404 });
    }

    const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
    let riskStatus = { overall_risk: "UNAVAILABLE", reasoning: "Risk assessment is temporarily unavailable.", flags: [] };
    try {
      const response = await fetch(`${baseUrl}/portfolio/risk-status`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Internal-Key": process.env.INTERNAL_API_KEY || "" },
        body: JSON.stringify({ portfolio: toAiHoldings(portfolio.holdings) }),
        signal: AbortSignal.timeout(5000),
      });
      if (response.ok) riskStatus = await response.json();
    } catch {
      // Portfolio facts remain available during a provider outage.
    }

    return NextResponse.json({
      ...portfolio,
      snapshotId: snapshot?.id ?? null,
      snapshotDate: snapshot?.created_at ?? null,
      coverageEnd: snapshot?.coverage_end ?? null,
      riskStatus,
    });
  } catch (error) {
    console.error("Portfolio load failed", error.code || error.name);
    return NextResponse.json({ error: "Failed to load portfolio", code: "INTERNAL_ERROR" }, { status: 500 });
  }
}
