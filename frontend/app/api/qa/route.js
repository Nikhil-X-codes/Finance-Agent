import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getLastSnapshot, getTradesSinceDate } from "@/lib/db";

function applyTradesToSnapshot(snapshotHoldings, trades) {
  const holdingsMap = new Map();
  for (const h of snapshotHoldings) {
    holdingsMap.set(h.ticker, { ...h, status: h.status || "UNREALIZED" });
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
        existing.status = "UNREALIZED";
      } else {
        holdingsMap.set(ticker, {
          ticker,
          name: "",
          isin: "",
          quantity: trade.quantity,
          avgBuyPrice: trade.price,
          assetType: "STOCK",
          sector: "",
          status: "UNREALIZED",
        });
      }
    } else if (trade.transaction_type === "SELL") {
      if (existing) {
        existing.quantity = Math.max(0, existing.quantity - trade.quantity);
        if (existing.quantity === 0) {
          existing.status = "REALIZED";
          existing.sellPrice = trade.price;
          existing.realizedPnl = (trade.price - existing.avgBuyPrice) * trade.quantity;
        }
      }
    }
  }

  return Array.from(holdingsMap.values());
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
        quantity: Number(h.quantity || 0),
        avg_buy_price: Number(h.avgBuyPrice || h.avg_buy_price || 0),
        asset_type: h.assetType || h.asset_type || "STOCK",
        sector: h.sector || "Other",
        status: h.status || (h.quantity === 0 ? "REALIZED" : "UNREALIZED"),
        current_price: h.currentPrice !== undefined && h.currentPrice !== null ? Number(h.currentPrice) : null,
        sell_price: h.sellPrice !== undefined && h.sellPrice !== null ? Number(h.sellPrice) : 0.0,
        realized_pnl: h.realizedPnl !== undefined && h.realizedPnl !== null ? Number(h.realizedPnl) : 0.0,
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
