import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getLastSnapshot, getTradesSinceDate } from "@/lib/db";

// Helper to merge trades and generate current holdings
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

    const body = await request.json().catch(() => ({}));
    const { proposed_trade } = body;

    if (
      !proposed_trade ||
      !proposed_trade.ticker ||
      !proposed_trade.action ||
      proposed_trade.quantity === undefined ||
      proposed_trade.price === undefined
    ) {
      return NextResponse.json(
        { error: "Missing proposed trade fields", code: "VALIDATION_ERROR" },
        { status: 422 }
      );
    }

    // Retrieve active portfolio
    let formattedHoldings = [];
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
        sector: h.sector || "Other",
      }));
    }

    // Offline Insufficient Quantity Check for SELL/TRIM/EXIT
    const actionUpper = proposed_trade.action.toUpperCase();
    const qty = Number(proposed_trade.quantity);
    if (actionUpper === "SELL" || actionUpper === "TRIM" || actionUpper === "EXIT") {
      const holding = formattedHoldings.find(
        (h) => h.ticker.toUpperCase() === proposed_trade.ticker.toUpperCase()
      );
      if (!holding || holding.quantity < qty) {
        return NextResponse.json({
          allowed: false,
          ticker: proposed_trade.ticker.toUpperCase(),
          action: actionUpper,
          quantity: qty,
          price: Number(proposed_trade.price),
          new_portfolio_weight: 0,
          limit_threshold: 0,
          warnings: [
            `Insufficient quantity to execute ${actionUpper}. You currently hold ${
              holding ? holding.quantity : 0
            } shares of ${proposed_trade.ticker.toUpperCase()} but attempted to sell/trim ${qty} shares.`,
          ],
          citations: ["Local Holdings Audit"],
        });
      }
    }

    const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
    const internalKey = process.env.INTERNAL_API_KEY || "";

    const aiResponse = await fetch(`${baseUrl}/validate-trade`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Key": internalKey,
      },
      body: JSON.stringify({
        user_id: session.userId,
        proposed_trade: {
          ticker: proposed_trade.ticker.toUpperCase(),
          action: actionUpper,
          quantity: qty,
          price: Number(proposed_trade.price),
        },
        portfolio: formattedHoldings,
      }),
    });

    if (!aiResponse.ok) {
      const errText = await aiResponse.ok ? "" : await aiResponse.text();
      return NextResponse.json(
        { error: errText || "Failed to validate trade", code: "VALIDATION_FAILED" },
        { status: aiResponse.status }
      );
    }

    const validationResult = await aiResponse.json();
    return NextResponse.json(validationResult);
  } catch (error) {
    console.error("Validate trade API error:", error);
    return NextResponse.json(
      { error: "Internal Server Error", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
