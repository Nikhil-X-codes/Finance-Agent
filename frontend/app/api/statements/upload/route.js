import { NextResponse } from "next/server";
import { createHash } from "node:crypto";
import { extname } from "node:path";
import { getSession } from "@/lib/auth";
import { createStatementPreview } from "@/lib/db";
import { validateParsedStatement } from "@/lib/statements";

const ALLOWED_EXTENSIONS = new Set([".pdf", ".xlsx", ".xls", ".csv"]);
const MAX_FILE_SIZE = 5 * 1024 * 1024;

export async function POST(request) {
  try {
    const session = await getSession();
    if (!session.userId) return NextResponse.json({ error: "UNAUTHORIZED", code: "UNAUTHORIZED" }, { status: 401 });

    const file = (await request.formData()).get("file");
    if (!file || typeof file === "string" || !ALLOWED_EXTENSIONS.has(extname(file.name).toLowerCase())) {
      return NextResponse.json({ error: "Upload a PDF, XLSX, XLS, or CSV statement.", code: "INVALID_FILE_TYPE" }, { status: 422 });
    }
    if (!file.size || file.size > MAX_FILE_SIZE) {
      return NextResponse.json({ error: "File must be between 1 byte and 5 MB.", code: "INVALID_FILE_SIZE" }, { status: 413 });
    }

    const statementKey = createHash("sha256").update(Buffer.from(await file.arrayBuffer())).digest("hex");
    const body = new FormData();
    body.append("file", file);
    const baseUrl = process.env.FASTAPI_URL || "http://localhost:8000";
    const upstream = await fetch(`${baseUrl}/parse-statement`, {
      method: "POST", headers: { "X-Internal-Key": process.env.INTERNAL_API_KEY || "" }, body,
    });
    if (upstream.status === 503) {
      return NextResponse.json({
        error: "Statement extraction is temporarily unavailable. Please try again shortly.",
        code: "PARSE_UNAVAILABLE",
      }, { status: 503 });
    }
    if (!upstream.ok) {
      const response = await upstream.json().catch(() => ({}));
      return NextResponse.json({
        error: upstream.status === 422 ? response.detail || "Could not read statement." : "Statement parsing failed.",
        code: "PARSE_FAILED",
      }, { status: upstream.status });
    }
    const parsed = validateParsedStatement(await upstream.json());
    if (!parsed.holdings.length && !parsed.tradeHistory.length) {
      return NextResponse.json({
        error: "No valid holdings or realized trades were found.", code: "NO_VALID_ROWS",
        unrecognizedRows: parsed.unrecognizedRows,
      }, { status: 422 });
    }
    const preview = await createStatementPreview(session.userId, statementKey, parsed);
    return NextResponse.json({ ...parsed, previewId: preview.id });
  } catch (error) {
    console.error("Statement upload failed", error.code || error.name);
    return NextResponse.json({ error: "Upload failed", code: "INTERNAL_ERROR" }, { status: 500 });
  }
}
