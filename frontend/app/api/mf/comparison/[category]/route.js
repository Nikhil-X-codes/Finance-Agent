import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET(request, { params }) {
  try {
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const { category } = params;
    
    // Parse the 'refresh' query param from the incoming URL
    const { searchParams } = new URL(request.url);
    const refresh = searchParams.get("refresh") === "true";

    const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
    const internalKey = process.env.INTERNAL_API_KEY || "";

    const aiResponse = await fetch(`${baseUrl}/mf/comparison/${encodeURIComponent(category)}?refresh=${refresh}`, {
      method: "GET",
      headers: {
        "X-Internal-Key": internalKey,
      },
    });

    if (!aiResponse.ok) {
      const payload = await aiResponse.json().catch(() => ({}));
      return NextResponse.json(
        { error: typeof payload.detail === "string" ? payload.detail : "Fund data is temporarily unavailable.", code: "FETCH_FAILED" },
        { status: aiResponse.status }
      );
    }

    const data = await aiResponse.json();
    
    // Map the fields from the backend format to what the frontend page expects
    if (data.funds && Array.isArray(data.funds)) {
      data.funds = data.funds.map(fund => ({
        ...fund,
        valuation: {
          pe: fund.others?.pe
        },
        expenseRatio: fund.others?.ter
      }));
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error("MF comparison API error:", error.code || error.name);
    return NextResponse.json(
      { error: "The fund service is unavailable. Try again when the AI service is running.", code: "AI_UNAVAILABLE" },
      { status: 503 }
    );
  }
}
