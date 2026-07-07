export async function GET() {
  const baseUrl = process.env.FASTAPI_URL || process.env.NEXT_PUBLIC_FASTAPI_URL || "http://localhost:8000";
  try {
    const response = await fetch(`${baseUrl}/health`, { cache: "no-store" });
    const payload = await response.json();
    return Response.json(payload, { status: response.status });
  } catch {
    return Response.json({ error: "AI_UNAVAILABLE", code: "AI_UNAVAILABLE" }, { status: 503 });
  }
}
