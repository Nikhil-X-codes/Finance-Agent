"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getStockDetail } from "@/lib/api";

const QUOTE_LABELS = {
  delayed: "Delayed quote", last_published: "Last published quote",
  stale_cache: "Cached quote", unavailable: "Quote unavailable", published: "Published quote",
  disabled: "Market data disabled", unsupported: "Quote unsupported",
};

const currency = (value) => value == null ? "Unavailable" : new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 2,
}).format(value);

const measurement = (value, suffix = "") => value == null ? "Unavailable" : value.toFixed(2) + suffix;

export default function StockDetailPage() {
  const { symbol } = useParams();
  const [stock, setStock] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getStockDetail(symbol)
      .then((result) => { if (active) setStock(result); })
      .catch((err) => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [symbol]);

  if (loading) {
    return <div className="space-y-6"><Skeleton className="h-44 bg-slate-800" /><Skeleton className="h-64 bg-slate-800" /></div>;
  }

  const back = <Link href="/stocks"><Button variant="ghost">← Back to Stocks</Button></Link>;
  if (error || !stock) {
    return <div className="space-y-6">{back}<Card className="border-red-900/40 p-6 text-red-400">{error || "Stock unavailable"}</Card></div>;
  }

  const change = stock.price?.change;
  const positive = change >= 0;
  const marketTime = stock.marketTimestamp ? new Date(stock.marketTimestamp) : null;
  const hasMarketTime = marketTime && !Number.isNaN(marketTime.getTime());
  const timestamp = hasMarketTime && new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata",
  }).format(marketTime);
  const fundamentals = stock.fundamentals || {};

  return (
    <div className="space-y-6">
      {back}
      <Card className="border-slate-800 bg-slate-900/30">
        <CardContent className="flex flex-wrap justify-between gap-4 p-6">
          <div>
            <h1 className="font-mono text-3xl font-bold text-slate-50">{stock.symbol}</h1>
            <p className="text-sm text-slate-400">{stock.name}</p>
            {stock.sector && stock.sector !== "Unknown" && <p className="text-xs text-slate-500">{stock.sector}</p>}
          </div>
          <div className="md:text-right">
            <p className="text-4xl font-bold text-slate-50">{currency(stock.price?.current)}</p>
            {change != null && stock.price.changePercent != null && (
              <p className={positive ? "text-sm text-emerald-400" : "text-sm text-rose-400"}>
                {positive ? "+" : ""}{change.toFixed(2)} ({stock.price.changePercent.toFixed(2)}%)
              </p>
            )}
            <p className="text-xs text-slate-400">
              {QUOTE_LABELS[stock.quoteStatus]}{timestamp && <> · {timestamp} IST</>}
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Previous close" value={currency(stock.price?.previousClose)} />
        <MetricCard label="52-week range" value={stock.price?.fiftyTwoWeekRange || "Unavailable"} />
        <MetricCard label="Price source" value={stock.source?.price} />
        <MetricCard label="Fundamentals source" value={stock.source?.fundamentals} />
      </div>

      {stock.history && stock.history.status !== "disabled" && <PriceHistory history={stock.history} />}

      <Card className="border-slate-800 bg-slate-900/30">
        <CardHeader><CardTitle className="text-lg text-slate-100">Company fundamentals</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
          <MetricCard label="P/E ratio" value={measurement(fundamentals.pe)} />
          <MetricCard label="P/B ratio" value={measurement(fundamentals.pb)} />
          <MetricCard label="ROE" value={measurement(fundamentals.roe, "%")} />
          <MetricCard label="ROCE" value={measurement(fundamentals.roce, "%")} />
          <MetricCard label="Debt to equity" value={measurement(fundamentals.debtToEquity)} />
          <MetricCard label="Dividend yield" value={measurement(fundamentals.dividendYield, "%")} />
        </CardContent>
      </Card>
    </div>
  );
}

function PriceHistory({ history }) {
  return (
    <Card className="border-slate-800 bg-slate-900/30">
      <CardHeader>
        <CardTitle className="text-lg text-slate-100">Daily closing price</CardTitle>
        {history.status === "available" && <CardDescription>{history.source} · Through {history.asOf}</CardDescription>}
      </CardHeader>
      <CardContent>
        {history.status === "available" ? (
          <>
            <div className="h-56" role="img" aria-label="Unadjusted daily closing prices in INR">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history.points}>
                  <CartesianGrid stroke="#334155" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(value) => value.slice(5)} stroke="#94a3b8" minTickGap={25} />
                  <YAxis domain={["auto", "auto"]} stroke="#94a3b8" width={55} />
                  <Tooltip formatter={(value) => [currency(value), "Close"]} />
                  <Line type="linear" dataKey="close" stroke="#38bdf8" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-3 text-xs text-slate-400">
              Chart shows unadjusted closes. {history.adjustedPriceReturnPercent == null
                ? "Split- and bonus-adjusted return unavailable."
                : <>Split- and bonus-adjusted price return {history.adjustedPriceReturnPercent.toFixed(2)}%, excluding dividends.</>}
            </p>
          </>
        ) : (
          <p className="text-sm text-slate-400">
            {history.status === "unsupported" ? "No daily price records for this symbol." : "Price history is temporarily unavailable."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-800/80 bg-slate-950/50 p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="font-medium text-slate-200">{value ?? "Unavailable"}</p>
    </div>
  );
}
