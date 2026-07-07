const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_INTERNAL_API_KEY || "";

async function fetchAPI(endpoint, options = {}) {
  const url = `${API_URL}${endpoint}`;
  
  const headers = {
    "Content-Type": "application/json",
    "X-Internal-Key": API_KEY,
    ...options.headers,
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || `HTTP ${response.status}`);
  }

  return response.json();
}

// Stock APIs
export const getPopularStocks = () => fetchAPI("/v1/stocks/popular");
export const searchStocks = (query) => fetchAPI(`/v1/stocks/search?q=${encodeURIComponent(query)}`);
export const getStockDetail = (symbol) => fetchAPI(`/v1/stocks/${symbol}`);

// Fund APIs
export const getFundCategories = () => fetchAPI("/mf/categories");
export const getFundComparison = (category, refresh = false) => fetchAPI(`/mf/comparison/${encodeURIComponent(category)}${refresh ? "?refresh=true" : ""}`);

// Portfolio APIs
export const parseStatement = (file) => {
  const formData = new FormData();
  formData.append("file", file);
  
  return fetch(`${API_URL}/parse-statement`, {
    method: "POST",
    headers: { "X-Internal-Key": API_KEY },
    body: formData,
  })
    .then(async (r) => {
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || err.error || `HTTP ${r.status}`);
      }
      return r.json();
    })
    .then((parseResult) => {
      const holdings = (parseResult.holdings || []).map((h) => ({
        ticker: h.ticker || "",
        name: h.name || "",
        quantity: h.quantity || 0,
        avgBuyPrice: h.avg_buy_price || 0,
        assetType: h.asset_type || "STOCK",
        sector: h.sector || "",
      }));

      return {
        previewId: `prev_${Math.random().toString(36).substr(2, 9)}`,
        brokerDetected: parseResult.broker_detected || "Unknown",
        parseConfidence: parseResult.confidence !== undefined ? parseResult.confidence : 0,
        holdings: holdings,
        unrecognizedRows: parseResult.unrecognized_rows || [],
        sectorAllocation: parseResult.sector_allocation || {}
      };
    });
};

// RAG API
export const queryRAG = (query, top_k = 5, min_score = 0.6) => 
  fetchAPI("/v1/rag", {
    method: "POST",
    body: JSON.stringify({ query, top_k, min_score }),
  });

// Trade Validation API
export const validateTrade = (user_id, trade, portfolio) =>
  fetchAPI("/validate-trade", {
    method: "POST",
    body: JSON.stringify({ user_id, proposed_trade: trade, portfolio }),
  });
