import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getReportById } from "@/lib/db";

export async function GET(request, { params }) {
  try {
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const { id } = params;
    if (!id) {
      return NextResponse.json(
        { error: "Report ID is required", code: "VALIDATION_ERROR" },
        { status: 420 }
      );
    }

    const report = getReportById(session.userId, id);
    if (!report) {
      return NextResponse.json(
        { error: "Report not found", code: "NOT_FOUND" },
        { status: 404 }
      );
    }

    // Return the report JSON directly matching the contract
    return NextResponse.json(report.report_json);
  } catch (error) {
    console.error("Get report by ID error:", error);
    return NextResponse.json(
      { error: "Internal Server Error", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
