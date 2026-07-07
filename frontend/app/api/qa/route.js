import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getLastSnapshot, getTradesSinceDate } from "@/lib/db";

function applyTradesToSnapshot(snapshotHoldings, trades) {
  const holdingsMap = new Map();
  for (const h of snapshotHoldings) {
    holdingsMap.set(h.ticker, { ...h });
  }

  for (const trade of trades) {
    const ticker = trade.ticker;
    const existing = holdingsMap.get(ticker);

    if (trade.transaction_type === "BUY") {
      if (existing) {
        const totalCost =
          existing.avgBuyPrice * existing.quantity + trade.price * trade.quantity;
        const totalQty = existing.quantity + trade.quantity;
        existing.quantity = totalQty;
        existing.avgBuyPrice = totalQty > 0 ? totalCost / totalQty : 0;
      } else {
        holdingsMap.set(ticker, {
          ticker,
          name: "",
          isin: "",
          quantity: trade.quantity,
          avgBuyPrice: trade.price,
          assetType: "STOCK",
          sector: "",
        });
      }
    } else if (trade.transaction_type === "SELL") {
      if (existing) {
        existing.quantity -= trade.quantity;
      }
    }
  }

  return Array.from(holdingsMap.values()).filter((h) => h.quantity > 0);
}

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
    const { question, conversationHistory = [] } = reqBody;

    if (!question) {
      return NextResponse.json(
        { error: "Question is required", code: "VALIDATION_ERROR" },
        { status: 422 }
      );
    }

    // Retrieve portfolio context (if user has one)
    let formattedHoldings = null;
    const snapshot = getLastSnapshot(session.userId);
    if (snapshot) {
      const trades = getTradesSinceDate(session.userId, snapshot.created_at);
      const mergedHoldings = applyTradesToSnapshot(snapshot.holdings_json, trades);
      formattedHoldings = mergedHoldings.map((h) => ({
        isin: h.isin || "INE000000000",
        ticker: h.ticker || "",
        name: h.name || h.ticker || "",
        quantity: Number(h.quantity),
        avg_buy_price: Number(h.avgBuyPrice),
        asset_type: h.assetType === "MUTUAL_FUND" ? "MUTUAL_FUND" : "STOCK",
        sector: h.sector || "Other"
      }));
    }

    // Map conversationHistory to FastAPI format
    const formattedHistory = conversationHistory.map((item) => ({
      role: item.role,
      content: item.content
    }));

    const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
    const internalKey = process.env.INTERNAL_API_KEY || "";

    const aiResponse = await fetch(`${baseUrl}/qa`, {
      method: "POST",
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

    const reader = aiResponse.body.getReader();
    const decoder = new TextDecoder("utf-8");
    const encoder = new TextEncoder();

    const stream = new ReadableStream({
      async start(controller) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              controller.close();
              break;
            }

            const chunkStr = decoder.decode(value, { stream: true });
            controller.enqueue(encoder.encode(chunkStr));
          }
        } catch (streamErr) {
          console.error("Stream reading error:", streamErr);
          try { controller.close(); } catch (_) {}
        }
      }
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
      },
    });

  } catch (error) {
    console.error("Q&A API error:", error);
    return NextResponse.json(
      { error: "Internal Server Error", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
