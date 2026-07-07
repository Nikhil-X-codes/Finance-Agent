import { NextResponse } from "next/server";
import { z } from "zod";
import { getSession } from "@/lib/auth";
import { getTradesByUser, createTrade } from "@/lib/db";
import fs from "fs";
import path from "path";

// Load lookups
let tickerMap = {};
try {
  const mapPath = path.join(process.cwd(), "../ai-service/data/lookups/ticker_sector_map.json");
  if (fs.existsSync(mapPath)) {
    tickerMap = JSON.parse(fs.readFileSync(mapPath, "utf-8"));
  }
} catch (e) {
  console.error("Failed to load ticker_sector_map.json", e);
}

const tradeSchema = z.object({
  ticker: z.string().min(1, "Ticker is required").transform((v) => v.toUpperCase()),
  transactionType: z.enum(["BUY", "SELL"], { required_error: "Must be BUY or SELL" }),
  quantity: z.number(),
  price: z.number(),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Date must be YYYY-MM-DD"),
});

export async function GET() {
  try {
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const trades = getTradesByUser(session.userId);

    return NextResponse.json({
      trades: trades.map((t) => ({
        id: t.id,
        ticker: t.ticker,
        transactionType: t.transaction_type,
        quantity: t.quantity,
        price: t.price,
        date: t.trade_date,
        createdAt: t.created_at,
      })),
    });
  } catch (error) {
    console.error("Get trades error:", error);
    return NextResponse.json(
      { error: "Failed to fetch trades", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
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

    const body = await request.json();
    const parsed = tradeSchema.safeParse(body);

    if (!parsed.success) {
      return NextResponse.json(
        { error: "VALIDATION_ERROR", details: parsed.error.flatten().fieldErrors },
        { status: 422 }
      );
    }

    const { ticker, transactionType, quantity, price, date } = parsed.data;

    // Validate ticker
    const validTickers = new Set(["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "AXISBANK", "MARUTI", "M&M", "ITC", "HUL"]);
    const isTickerInMap = Object.keys(tickerMap).length > 0 ? !!tickerMap[ticker] : validTickers.has(ticker);
    if (!isTickerInMap) {
      return NextResponse.json(
        { error: "Ticker not found. Check NSE symbol.", code: "TICKER_NOT_FOUND" },
        { status: 422 }
      );
    }

    // Validate quantity is positive
    if (quantity <= 0) {
      return NextResponse.json(
        { error: "Quantity must be a positive number", code: "INVALID_QUANTITY" },
        { status: 422 }
      );
    }

    // Validate price is positive
    if (price <= 0) {
      return NextResponse.json(
        { error: "Price must be a positive number", code: "INVALID_PRICE" },
        { status: 422 }
      );
    }

    // Validate date is not in the future
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");
    const dd = String(today.getDate()).padStart(2, "0");
    const todayStr = `${yyyy}-${mm}-${dd}`;
    if (date > todayStr) {
      return NextResponse.json(
        { error: "Trade date cannot be in the future", code: "FUTURE_DATE" },
        { status: 422 }
      );
    }

    const trade = createTrade(session.userId, ticker, transactionType, quantity, price, date);

    return NextResponse.json(
      {
        id: trade.id,
        ticker: trade.ticker,
        transactionType: trade.transaction_type,
        quantity: trade.quantity,
        price: trade.price,
        date: trade.trade_date,
        createdAt: trade.created_at,
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("Create trade error:", error);
    return NextResponse.json(
      { error: "Failed to create trade", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
