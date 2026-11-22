import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET(request) {
  try {
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
    const internalKey = process.env.INTERNAL_API_KEY || "";

    const aiResponse = await fetch(`${baseUrl}/v1/stocks/popular`, {
      method: "GET",
      headers: {
        "X-Internal-Key": internalKey,
      },
    });

    if (!aiResponse.ok) {
      const payload = await aiResponse.json().catch(() => ({}));
      return NextResponse.json(
        { error: typeof payload.detail === "string" ? payload.detail : "Market movers are temporarily unavailable.", code: "FETCH_FAILED" },
        { status: aiResponse.status }
      );
    }

    const data = await aiResponse.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Market movers API error:", error.code || error.name);
    return NextResponse.json(
      { error: "The market data service is unavailable. Try again when the AI service is running.", code: "AI_UNAVAILABLE" },
      { status: 503 }
    );
  }
}
