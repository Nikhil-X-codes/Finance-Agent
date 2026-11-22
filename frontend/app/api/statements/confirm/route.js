import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { confirmStatement, PortfolioConflict } from "@/lib/db";
import { confirmSchema } from "@/lib/statements";

export async function POST(request) {
  try {
    const session = await getSession();
    if (!session.userId) return NextResponse.json({ error: "UNAUTHORIZED", code: "UNAUTHORIZED" }, { status: 401 });

    const parsed = confirmSchema.safeParse(await request.json().catch(() => null));
    if (!parsed.success) {
      return NextResponse.json({
        error: parsed.error.issues[0]?.message || "Review the statement rows and dates.",
        code: "VALIDATION_ERROR",
      }, { status: 422 });
    }

    const { previewId, holdings, coverageStart, coverageEnd } = parsed.data;
    const snapshot = await confirmStatement(session.userId, previewId, holdings, coverageStart || null, coverageEnd);
    if (!snapshot) return NextResponse.json({ error: "Statement preview not found.", code: "NOT_FOUND" }, { status: 404 });

    return NextResponse.json({
      snapshotId: snapshot.id, holdingsCount: snapshot.holdings_count, createdAt: snapshot.created_at,
    }, { status: 201 });
  } catch (error) {
    if (error instanceof PortfolioConflict) {
      return NextResponse.json({ error: error.message, code: error.code }, { status: 409 });
    }
    console.error("Statement confirmation failed", error.code || error.name);
    return NextResponse.json({ error: "Confirmation failed", code: "INTERNAL_ERROR" }, { status: 500 });
  }
}
