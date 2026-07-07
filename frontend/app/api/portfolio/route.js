import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getLastSnapshot, getTradesSinceDate } from "@/lib/db";

/**
 * Merge trade deltas into a snapshot to produce the current portfolio.
 * BUY  → increases quantity, recalculates weighted avg price
 * SELL → decreases quantity (avg price unchanged)
 * Holdings with quantity ≤ 0 are removed.
 */
function applyTradesToSnapshot(snapshotHoldings, trades) {
  // Build a map keyed by ticker for O(1) lookups of active holdings only
  const holdingsMap = new Map();
  const activeHoldings = (snapshotHoldings || []).filter(
    (h) => h.status !== "REALIZED" && h.quantity > 0
  );
  for (const h of activeHoldings) {
    holdingsMap.set(h.ticker, { ...h });
  }

  for (const trade of trades) {
    const ticker = trade.ticker;
    const existing = holdingsMap.get(ticker);

    if (trade.transaction_type === "BUY") {
      if (existing) {
        // Weighted average price
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
      // If no existing holding, ignore the sell (edge case)
    }
  }

  // Filter out zero/negative quantity holdings
  return Array.from(holdingsMap.values()).filter((h) => h.quantity > 0);
}

export async function GET() {
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

    // Get trades created since the snapshot
    const trades = getTradesSinceDate(session.userId, snapshot.created_at);

    // Merge trades into snapshot (active holdings only)
    const mergedHoldings = applyTradesToSnapshot(snapshot.holdings_json, trades);

    // Extract realized trades from the snapshot
    const tradeHistory = (snapshot.holdings_json || [])
      .filter((h) => h.status === "REALIZED")
      .map((t) => ({
        ticker: t.ticker || "",
        name: t.name || "",
        quantity: t.quantity || 0,
        avgBuyPrice: t.avgBuyPrice || 0,
        sellPrice: t.sellPrice || 0,
        realizedPnl: t.realizedPnl || 0,
        buyDate: t.buyDate || "",
        sellDate: t.sellDate || "",
        status: "REALIZED",
      }));

    // Compute value-weighted sector allocation
    const sectorAllocation = {};
    let totalValue = 0;
    for (const h of mergedHoldings) {
      const val = Number(h.quantity || 0) * Number(h.avgBuyPrice || 0);
      totalValue += val;
      const sector = h.sector || "Other";
      sectorAllocation[sector] = (sectorAllocation[sector] || 0) + val;
    }
    // Normalize to percentages (0 to 100)
    for (const sector of Object.keys(sectorAllocation)) {
      sectorAllocation[sector] = totalValue > 0
        ? Math.round((sectorAllocation[sector] / totalValue) * 10000) / 100
        : 0;
    }

    // Calculate realized P&L total
    const realizedPnlTotal = tradeHistory.reduce((sum, t) => sum + (t.realizedPnl || 0), 0);

    return NextResponse.json({
      snapshotId: snapshot.id,
      snapshotDate: snapshot.created_at,
      tradesMergedCount: trades.length,
      holdings: mergedHoldings,
      tradeHistory,
      realizedPnlTotal,
      sectorAllocation,
    });
  } catch (error) {
    console.error("Portfolio error:", error);
    return NextResponse.json(
      { error: "Failed to load portfolio", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
