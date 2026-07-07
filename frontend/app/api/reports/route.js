import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getReportsByUser } from "@/lib/db";

export async function GET() {
  try {
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const reports = getReportsByUser(session.userId);
    const mapped = reports.map((row) => ({
      id: row.id,
      createdAt: row.created_at || row.report_json?.createdAt,
      overallRiskLevel: row.report_json?.portfolioSummary?.overallRiskLevel || "LOW",
      generatedVia: row.generated_via || "LLM",
    }));

    return NextResponse.json({ reports: mapped });
  } catch (error) {
    console.error("List reports error:", error);
    return NextResponse.json(
      { error: "Internal Server Error", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
