import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import path from "path";
import fs from "fs";
import os from "os";
import crypto from "crypto";

const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB

export async function POST(request) {
  try {
    // Auth check
    const session = await getSession();
    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", code: "UNAUTHORIZED" },
        { status: 401 }
      );
    }

    const formData = await request.formData();
    const file = formData.get("file");

    if (!file || typeof file === "string") {
      return NextResponse.json(
        { error: "No file provided", code: "INVALID_FILE_TYPE" },
        { status: 422 }
      );
    }

    const ALLOWED_MIME_TYPES = new Set([
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/vnd.ms-excel",
      "text/csv",
      "application/octet-stream"
    ]);

    const ALLOWED_EXTENSIONS = new Set([
      ".pdf",
      ".xlsx",
      ".xls",
      ".csv"
    ]);

    const ext = path.extname(file.name).toLowerCase();

    // Validate type
    if (!ALLOWED_MIME_TYPES.has(file.type) && !ALLOWED_EXTENSIONS.has(ext)) {
      return NextResponse.json(
        { error: "Only PDF, XLSX, XLS, and CSV files are accepted", code: "INVALID_FILE_TYPE" },
        { status: 422 }
      );
    }

    // Validate size
    if (file.size > MAX_FILE_SIZE) {
      return NextResponse.json(
        { error: "File must be under 5MB", code: "FILE_TOO_LARGE" },
        { status: 413 }
      );
    }

    // Save to temp directory preserving suffix
    const buffer = Buffer.from(await file.arrayBuffer());
    const tempFileName = `${crypto.randomUUID()}${ext}`;
    const tempFilePath = path.join(os.tmpdir(), tempFileName);
    fs.writeFileSync(tempFilePath, buffer);

    try {
      // Forward to FastAPI /parse-statement
      const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
      const internalKey = process.env.INTERNAL_API_KEY || "";

      const forwardFormData = new FormData();
      forwardFormData.append("file", new Blob([buffer], { type: file.type }), file.name);

      const aiResponse = await fetch(`${baseUrl}/parse-statement`, {
        method: "POST",
        headers: {
          "X-Internal-Key": internalKey,
        },
        body: forwardFormData,
      });

      if (!aiResponse.ok) {
        const errorData = await aiResponse.json().catch(() => ({}));
        return NextResponse.json(
          {
            error: errorData.error || "PDF parsing failed",
            code: errorData.code || "PARSE_FAILED",
          },
          { status: aiResponse.status }
        );
      }

      const parseResult = await aiResponse.json();

      const previewId = `prev_${crypto.randomUUID().slice(0, 12)}`;

      const holdings = (parseResult.holdings || []).map(h => ({
        isin: h.isin || "",
        ticker: h.ticker || "",
        name: h.name || "",
        quantity: h.quantity || 0,
        avgBuyPrice: h.avg_buy_price || 0,
        assetType: h.asset_type || "STOCK",
        sector: h.sector || "",
        status: h.status || "UNREALIZED",
        currentPrice: h.current_price || h.avg_buy_price,
        realizedPnl: h.realized_pnl || 0,
        buyDate: h.buy_date || "",
        sellDate: h.sell_date || "",
      }));

      const tradeHistory = (parseResult.realized_trades || []).map(t => ({
        isin: t.isin || "",
        ticker: t.ticker || "",
        name: t.name || "",
        quantity: t.quantity || 0,
        avgBuyPrice: t.buy_price || 0,
        sellPrice: t.sell_price || 0,
        realizedPnl: t.realized_pnl || 0,
        buyDate: t.buy_date || "",
        sellDate: t.sell_date || "",
        status: "REALIZED",
      }));

      return NextResponse.json({
        previewId,
        brokerDetected: parseResult.broker_detected || "Unknown",
        parseConfidence: parseResult.confidence !== undefined ? parseResult.confidence : 0,
        holdings: holdings,
        tradeHistory: tradeHistory,
        unrecognizedRows: parseResult.unrecognized_rows || [],
        sectorAllocation: parseResult.sector_allocation || {}
      });
    } finally {
      // Clean up temp file
      try {
        fs.unlinkSync(tempFilePath);
      } catch {
        // Ignore cleanup errors
      }
    }
  } catch (error) {
    console.error("Upload error:", error);

    // Handle FastAPI connection errors gracefully
    if (error.cause?.code === "ECONNREFUSED" || error.message?.includes("fetch failed")) {
      return NextResponse.json(
        { error: "AI service unavailable. Please try again later.", code: "AI_UNAVAILABLE" },
        { status: 503 }
      );
    }

    return NextResponse.json(
      { error: "Upload failed", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
