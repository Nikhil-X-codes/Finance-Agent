async function fetchAPI(endpoint, options) {
  const response = await fetch(endpoint, options);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }

  return payload;
}

export const getPopularStocks = (signal) => fetchAPI("/api/stocks/popular", { signal });
export const searchStocks = (query, signal) => fetchAPI(`/api/stocks/search?q=${encodeURIComponent(query)}`, { signal });
export const getStockDetail = (symbol) => fetchAPI(`/api/stocks/${encodeURIComponent(symbol)}`);
export const getFundCategories = (signal) => fetchAPI("/api/mf/categories", { signal });
export const getFundComparison = (category, refresh = false, signal) =>
  fetchAPI(`/api/mf/comparison/${encodeURIComponent(category)}?refresh=${refresh}`, { signal });

export const validateTrade = (trade) =>
  fetchAPI("/api/trades/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ proposed_trade: trade }),
  });
