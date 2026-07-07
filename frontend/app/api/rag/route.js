import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";

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
    const { query, top_k = 5, min_score = 0.6 } = reqBody;

    if (!query || typeof query !== "string") {
      return NextResponse.json(
        { error: "Query is required", code: "VALIDATION_ERROR" },
        { status: 422 }
      );
    }

    const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
    const internalKey = process.env.INTERNAL_API_KEY || "";

    const aiResponse = await fetch(`${baseUrl}/v1/rag`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Key": internalKey,
      },
      body: JSON.stringify({
        query: query,
        top_k: Number(top_k),
        min_score: Number(min_score),
      }),
    });

    if (!aiResponse.ok) {
      const errText = await aiResponse.text();
      return NextResponse.json(
        { error: errText || "Failed to fetch RAG results from AI service", code: "RAG_FAILED" },
        { status: aiResponse.status }
      );
    }

    const data = await aiResponse.json();

    // Map backend's 'text' property to 'content' to support display of results[0].content
    if (data.results && Array.isArray(data.results)) {
      data.results = data.results.map((r) => ({
        ...r,
        content: r.text || "",
      }));
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error("RAG API error:", error);
    return NextResponse.json(
      { error: "Internal Server Error", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
