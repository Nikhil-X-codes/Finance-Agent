"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { getPopularStocks, searchStocks } from "@/lib/api";

export default function StocksPage() {
  const [popularStocks, setPopularStocks] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  // Load popular stocks on mount
  useEffect(() => {
    fetchPopular();
  }, []);

  const fetchPopular = async () => {
    setLoading(true);
    try {
      const data = await getPopularStocks();
      setPopularStocks(data.stocks || []);
    } catch (err) {
      console.error("Failed to load popular stocks:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setSearchLoading(true);
    setSearched(true);
    try {
      const data = await searchStocks(searchQuery);
      setSearchResults(data.results || []);
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setSearchLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-50">Stock Explorer</h1>
        <p className="text-sm text-slate-400">
          Search details, live quotes, and fundamental valuation metrics for Indian equities.
        </p>
      </div>

      {/* Search Bar */}
      <Card className="border-slate-800 bg-slate-900/30 backdrop-blur-sm">
        <CardContent className="pt-6">
          <form onSubmit={handleSearch} className="flex gap-3">
            <Input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name or symbol (e.g. RELIANCE, HDFC Bank, TCS)..."
              className="flex-1 border-slate-800 bg-slate-950 text-slate-100 placeholder:text-slate-500"
            />
            <Button
              type="submit"
              disabled={searchLoading}
              className="bg-slate-50 text-slate-900 hover:bg-slate-200"
            >
              {searchLoading ? "Searching..." : "Search"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Search Results */}
      {searched && (
        <div className="space-y-4">
          <h2 className="text-lg font-medium text-slate-100">
            Search Results {searchResults.length > 0 && `(${searchResults.length})`}
          </h2>
          {searchLoading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-36 w-full bg-slate-900/80 border border-slate-800/80 rounded-xl" />
              ))}
            </div>
          ) : searchResults.length > 0 ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {searchResults.map((stock) => (
                <StockCard key={stock.symbol} stock={stock} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">No stocks found matching &quot;{searchQuery}&quot;.</p>
          )}
        </div>
      )}

      {/* Popular Stocks */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium text-slate-100">Popular Equities</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchPopular}
            className="text-xs text-sky-400 hover:text-sky-300 hover:bg-slate-900"
          >
            Refresh
          </Button>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-36 w-full bg-slate-900/80 border border-slate-800/80 rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {popularStocks.map((stock) => (
              <StockCard key={stock.symbol} stock={stock} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StockCard({ stock }) {
  if (stock.error) {
    return (
      <Card className="border-red-900/40 bg-red-950/10 p-4 rounded-xl flex flex-col justify-between h-36">
        <div>
          <h3 className="font-semibold text-red-400 text-lg font-mono">{stock.symbol}</h3>
          <p className="text-xs text-red-500 mt-2">Unavailable</p>
        </div>
        <p className="text-[10px] text-red-900 truncate">{stock.error}</p>
      </Card>
    );
  }

  const isPositive = (stock.change || 0) >= 0;

  const formatPrice = (p) =>
    p !== null && p !== undefined
      ? `₹${p.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
      : "—";

  const formatPercent = (v) => {
    if (v === null || v === undefined) return "—";
    const sign = v >= 0 ? "+" : "";
    return `${sign}${v.toFixed(2)}%`;
  };

  return (
    <Link href={`/stocks/${stock.symbol}`}>
      <Card className="border-slate-800 bg-slate-900/40 hover:bg-slate-800/30 hover:border-slate-700/80 transition-all cursor-pointer rounded-xl flex flex-col justify-between h-36 p-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="font-semibold text-slate-100 text-lg font-mono tracking-tight">{stock.symbol}</h3>
            <p className="text-xs text-slate-400 truncate mt-0.5">{stock.name}</p>
          </div>
          {stock.sector && stock.sector.toLowerCase() !== "unknown" && (
            <span className="text-[9px] font-medium px-2 py-0.5 bg-slate-950 text-slate-400 border border-slate-800 rounded-full shrink-0">
              {stock.sector}
            </span>
          )}
        </div>

        {/* Pricing */}
        <div className="my-2">
          <p className="text-2xl font-bold text-slate-50 font-mono tracking-tight">
            {formatPrice(stock.price)}
          </p>
          <p className={`text-xs font-mono font-medium ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
            {isPositive ? "+" : ""}{stock.change?.toFixed(2) || "0.00"} ({formatPercent(stock.changePercent)})
          </p>
        </div>

        {stock.matchType && (
          <p className="text-[9px] text-slate-500 font-mono mt-1 text-right">{stock.matchType}</p>
        )}
      </Card>
    </Link>
  );
}
