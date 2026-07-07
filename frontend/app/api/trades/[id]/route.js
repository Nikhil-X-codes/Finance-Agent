import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { deleteTradeById } from "@/lib/db";

export async function DELETE(_request, { params }) {
  try {
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const { id } = params;

    const result = deleteTradeById(session.userId, id);
    if (!result || !result.deleted) {
      if (result?.reason === "FORBIDDEN") {
        return NextResponse.json(
          { error: "Forbidden", code: "FORBIDDEN" },
          { status: 403 }
        );
      }
      return NextResponse.json(
        { error: "Trade not found", code: "NOT_FOUND" },
        { status: 404 }
      );
    }

    return NextResponse.json({ deleted: true });
  } catch (error) {
    console.error("Delete trade error:", error);
    return NextResponse.json(
      { error: "Failed to delete trade", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
