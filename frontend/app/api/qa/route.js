import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getPortfolio } from "@/lib/db";
import { toAiHoldings } from "@/lib/portfolio";

export async function POST(request) {
  try {
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const reqBody = await request.json().catch(() => ({}));
    const question = typeof reqBody?.question === "string" ? reqBody.question.trim() : "";
    const conversationHistory = Array.isArray(reqBody?.conversationHistory) ? reqBody.conversationHistory : [];

    if (!question || question.length > 3000) {
      return NextResponse.json(
        { error: "Enter a question between 1 and 3000 characters.", code: "VALIDATION_ERROR" },
        { status: 422 }
      );
    }

    const { holdings, tradeHistory } = await getPortfolio(session.userId);
    const formattedHoldings = toAiHoldings([...holdings, ...tradeHistory]);

    // Map conversationHistory to FastAPI format
    const formattedHistory = conversationHistory
      .filter((item) => item && ["user", "assistant"].includes(item.role) && typeof item.content === "string")
      .slice(-8).map((item) => ({
      role: item.role,
      content: item.content.slice(0, 8000)
    }));

    const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
    const internalKey = process.env.INTERNAL_API_KEY || "";

    const aiResponse = await fetch(`${baseUrl}/qa`, {
      method: "POST",
      signal: request.signal,
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Key": internalKey,
      },
      body: JSON.stringify({
        user_id: session.userId,
        question: question,
        portfolio_context: formattedHoldings,
        conversation_history: formattedHistory
      }),
    });

    if (!aiResponse.ok) {
      return NextResponse.json(
        { error: "FastAPI Q&A failed", code: "GENERATION_FAILED" },
        { status: aiResponse.status }
      );
    }

    return new Response(aiResponse.body, {
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-store" },
    });

  } catch (error) {
    console.error("Q&A API error:", error);
    return NextResponse.json(
      { error: "Internal Server Error", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
