"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getStockDetail } from "@/lib/api";

export default function StockDetailPage() {
  const params = useParams();
  const symbol = params.symbol;
  const [stock, setStock] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchStock();
  }, [symbol]);

  const fetchStock = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getStockDetail(symbol);
      setStock(data);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-6 w-32 bg-slate-800" />
        <Skeleton className="h-44 w-full bg-slate-900 border border-slate-800 rounded-xl" />
        <Skeleton className="h-64 w-full bg-slate-900 border border-slate-800 rounded-xl" />
      </div>
    );
  }

  if (error || !stock) {
    return (
      <div className="space-y-6">
        <Link href="/stocks">
          <Button variant="ghost" size="sm" className="text-slate-400 hover:text-slate-200 gap-2">
            ← Back to Stocks
          </Button>
        </Link>
        <Card className="border-red-900/40 bg-red-950/20 p-6 text-center text-red-400">
          {error || `Stock ${symbol.toUpperCase()} not found`}
        </Card>
      </div>
    );
  }

  const isPositive = (stock.price?.change || 0) >= 0;

  return (
    <div className="space-y-6">
      {/* Back Navigation */}
      <Link href="/stocks">
        <Button variant="ghost" size="sm" className="text-slate-400 hover:text-slate-200 gap-2 hover:bg-slate-900/50">
          ← Back to Stocks
        </Button>
      </Link>

      {/* Main Stock Summary Card */}
      <Card className="border-slate-800 bg-slate-900/30 backdrop-blur-sm">
        <CardContent className="p-6">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div className="space-y-2">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-3xl font-bold tracking-tight text-slate-50 font-mono">
                  {stock.symbol}
                </h1>
                {stock.sector && stock.sector.toLowerCase() !== "unknown" && (
                  <span className="px-3 py-0.5 bg-slate-950 text-slate-400 text-xs font-medium border border-slate-800 rounded-full">
                    {stock.sector}
                  </span>
                )}
              </div>
              <p className="text-slate-400 text-sm">{stock.name}</p>
            </div>

            <div className="text-left md:text-right space-y-1">
              <p className="text-4xl font-bold text-slate-50 font-mono tracking-tight">
                ₹{stock.price?.current?.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </p>
              <p className={`text-sm font-mono font-medium ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                {isPositive ? "+" : ""}{stock.price?.change?.toFixed(2) || "0.00"} ({isPositive ? "+" : ""}{stock.price?.changePercent?.toFixed(2) || "0.00"}%)
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Market Details & Sources */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Previous Close" value={`₹${stock.price?.previousClose?.toLocaleString("en-IN")}`} />
        <MetricCard label="52-Week Range" value={stock.price?.fiftyTwoWeekRange || "—"} />
        <MetricCard label="Price Feed Source" value={stock.source?.price} />
        <MetricCard label="Fundamentals Source" value={stock.source?.fundamentals} />
      </div>

      {/* Fundamentals Section */}
      <Card className="border-slate-800 bg-slate-900/30 backdrop-blur-sm">
        <CardHeader className="border-b border-slate-800/80 pb-4">
          <CardTitle className="text-lg font-medium text-slate-100">Company Fundamentals</CardTitle>
          <CardDescription className="text-slate-400">
            Valuation ratios and returns parsed from live exchange reports.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-6">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <MetricCard label="P/E Ratio" value={stock.fundamentals?.pe ? stock.fundamentals.pe.toFixed(2) : "—"} />
            <MetricCard label="P/B Ratio" value={stock.fundamentals?.pb ? stock.fundamentals.pb.toFixed(2) : "—"} />
            <MetricCard label="ROE" value={stock.fundamentals?.roe ? `${stock.fundamentals.roe.toFixed(1)}%` : "—"} />
            <MetricCard label="ROCE" value={stock.fundamentals?.roce ? `${stock.fundamentals.roce.toFixed(1)}%` : "—"} />
            <MetricCard label="Debt to Equity" value={stock.fundamentals?.debtToEquity ? stock.fundamentals.debtToEquity.toFixed(2) : "—"} />
            <MetricCard label="Dividend Yield" value={stock.fundamentals?.dividendYield ? `${stock.fundamentals.dividendYield.toFixed(2)}%` : "—"} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="bg-slate-950/50 rounded-xl border border-slate-800/80 p-4 space-y-1.5">
      <p className="text-xs text-slate-500 font-medium">{label}</p>
      <p className="text-lg font-semibold text-slate-200 font-mono">{value}</p>
    </div>
  );
}
