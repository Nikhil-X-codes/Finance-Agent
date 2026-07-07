export async function fetchJson(path, options = {}) {
  const baseUrl = process.env.NEXT_PUBLIC_FASTAPI_URL || process.env.FASTAPI_URL || "http://localhost:8000";
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  return response.json();
}
