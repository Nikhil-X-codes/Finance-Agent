import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getLastSnapshot, getTradesSinceDate, createReport } from "@/lib/db";

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

    const snapshot = getLastSnapshot(session.userId);
    if (!snapshot) {
      return NextResponse.json(
        { error: "No portfolio found. Upload a statement to get started.", code: "NO_PORTFOLIO" },
        { status: 404 }
      );
    }

    const trades = getTradesSinceDate(session.userId, snapshot.created_at);
    const mergedHoldings = applyTradesToSnapshot(snapshot.holdings_json, trades);

    // Map merged holdings to format expected by FastAPI's Holding model
    const formattedHoldings = mergedHoldings.map((h) => ({
      isin: h.isin || "INE000000000",
      ticker: h.ticker || "",
      name: h.name || h.ticker || "",
      quantity: Number(h.quantity),
      avg_buy_price: Number(h.avgBuyPrice),
      asset_type: h.assetType === "MUTUAL_FUND" ? "MUTUAL_FUND" : "STOCK",
      sector: h.sector || "Other",
      status: h.status || (h.quantity === 0 ? "REALIZED" : "UNREALIZED"),
      current_price: h.currentPrice || h.avgBuyPrice,
      sell_price: h.sellPrice || 0.0,
      realized_pnl: h.realizedPnl || 0.0
    }));

    const reqBody = await request.json().catch(() => ({}));
    const includeNews = reqBody.includeNews !== false;

    const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
    const internalKey = process.env.INTERNAL_API_KEY || "";

    const aiResponse = await fetch(`${baseUrl}/generate-report`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Key": internalKey,
      },
      body: JSON.stringify({
        user_id: session.userId,
        portfolio: formattedHoldings,
        include_news: includeNews,
      }),
    });

    if (!aiResponse.ok) {
      return NextResponse.json(
        { error: "FastAPI report generation failed", code: "GENERATION_FAILED" },
        { status: aiResponse.status }
      );
    }

    const reader = aiResponse.body.getReader();
    const decoder = new TextDecoder("utf-8");
    const encoder = new TextEncoder();

    let buffer = "";

    const stream = new ReadableStream({
      async start(controller) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              if (buffer) {
                controller.enqueue(encoder.encode(buffer));
              }
              controller.close();
              break;
            }

            const chunkStr = decoder.decode(value, { stream: true });
            buffer += chunkStr;

            let boundary = buffer.indexOf("\n\n");
            while (boundary !== -1) {
              const rawMessage = buffer.slice(0, boundary + 2);
              buffer = buffer.slice(boundary + 2);

              const lines = rawMessage.split("\n");
              let eventName = "";
              let dataStr = "";

              for (const line of lines) {
                if (line.startsWith("event: ")) {
                  eventName = line.slice(7).trim();
                } else if (line.startsWith("data: ")) {
                  dataStr = line.slice(6).trim();
                }
              }

              if (eventName === "complete" && dataStr) {
                try {
                  const completeData = JSON.parse(dataStr);
                  const reportJson = completeData.report_json;
                  if (reportJson) {
                    createReport(
                      session.userId,
                      snapshot.id,
                      reportJson,
                      completeData.generatedVia || "LLM"
                    );
                  }
                } catch (err) {
                  console.error("Error saving report to DB:", err);
                }
              }

              controller.enqueue(encoder.encode(rawMessage));
              boundary = buffer.indexOf("\n\n");
            }
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
    console.error("Generate report API error:", error);
    return NextResponse.json(
      { error: "Internal Server Error", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
