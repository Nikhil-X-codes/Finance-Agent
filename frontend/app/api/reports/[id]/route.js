import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getReportById, updateReport, deleteReport } from "@/lib/db";

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

    // Return the report JSON directly matching the contract, injecting report ID and customized name if available
    const responseData = {
      ...report.report_json,
      id: report.id,
      name: report.report_json.name || `Report ${new Date(report.created_at).toLocaleDateString()}`
    };
    return NextResponse.json(responseData);
  } catch (error) {
    console.error("Get report by ID error:", error);
    return NextResponse.json(
      { error: "Internal Server Error", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}

export async function PUT(request, { params }) {
  try {
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const { id } = params;
    const body = await request.json().catch(() => ({}));
    const { name } = body;

    if (!name || !name.trim()) {
      return NextResponse.json(
        { error: "Report name is required", code: "VALIDATION_ERROR" },
        { status: 422 }
      );
    }

    const report = getReportById(session.userId, id);
    if (!report) {
      return NextResponse.json(
        { error: "Report not found", code: "NOT_FOUND" },
        { status: 404 }
      );
    }

    const updatedReportJson = {
      ...report.report_json,
      name: name.trim()
    };

    const success = updateReport(session.userId, id, updatedReportJson);
    if (!success) {
      throw new Error("Failed to update report in database");
    }

    return NextResponse.json({ success: true, name: name.trim() });
  } catch (error) {
    console.error("Update report error:", error);
    return NextResponse.json(
      { error: "Internal Server Error", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}

export async function DELETE(request, { params }) {
  try {
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const { id } = params;
    const success = deleteReport(session.userId, id);
    if (!success) {
      return NextResponse.json(
        { error: "Report not found or delete failed", code: "NOT_FOUND" },
        { status: 404 }
      );
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Delete report error:", error);
    return NextResponse.json(
      { error: "Internal Server Error", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
