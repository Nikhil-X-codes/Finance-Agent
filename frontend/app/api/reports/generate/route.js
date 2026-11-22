import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { createReport, getPortfolio } from "@/lib/db";
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

    const { snapshot, holdings, tradeHistory, tradesMergedCount } = await getPortfolio(session.userId);
    if (!snapshot && !tradesMergedCount) {
      return NextResponse.json(
        { error: "No portfolio found. Upload a statement or record a trade.", code: "NO_PORTFOLIO" },
        { status: 404 }
      );
    }

    const formattedHoldings = toAiHoldings([...holdings, ...tradeHistory]);

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

              if (eventName === "complete") {
                try {
                  const completeData = JSON.parse(dataStr);
                  const reportJson = completeData.report_json;
                  if (!reportJson?.id) throw new Error("Report result did not include an ID");
                  await createReport(session.userId, snapshot?.id ?? null, reportJson, completeData.generatedVia || "LLM");
                } catch (error) {
                  console.error("Report persistence failed", error.code || error.name);
                  controller.enqueue(encoder.encode('event: error\ndata: {"error":"Report could not be saved.","code":"SAVE_FAILED"}\n\n'));
                  controller.close();
                  await reader.cancel();
                  return;
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
