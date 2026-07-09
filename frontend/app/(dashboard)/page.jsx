"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

export default function DashboardHomePage() {
  const router = useRouter();
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchPortfolio = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/portfolio");
      if (res.status === 404) {
        setPortfolio(null);
        setError(null);
        return;
      }
      if (!res.ok) throw new Error("Failed to fetch dashboard data");
      const data = await res.json();
      setPortfolio(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPortfolio();
  }, [fetchPortfolio]);

  const getRiskBadgeColor = (level) => {
    switch (level?.toUpperCase()) {
      case "HIGH":
        return "bg-red-500/20 text-red-400 border-red-500/30";
      case "MEDIUM":
        return "bg-amber-500/20 text-amber-400 border-amber-500/30";
      default:
        return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
    }
  };

  if (loading) {
    return <DashboardHomeSkeleton />;
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-900/50 bg-red-950/20 p-6 text-center text-red-400">
        {error}
      </div>
    );
  }

  if (!portfolio) {
    return (
      <div className="space-y-6">
        {/* Welcome Header */}
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-50">Welcome to Portfolio Advisor</h1>
          <p className="text-sm text-slate-400">
            Let's get started. Connect your broker statement or log your trades to analyze your risk concentration.
          </p>
        </div>

        {/* Quick Setup Options Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
          <Card className="border-slate-800 bg-slate-900/20 hover:bg-slate-900/35 transition-colors cursor-pointer" onClick={() => router.push("/portfolio/upload")}>
            <CardHeader className="space-y-2">
              <div className="h-10 w-10 rounded-lg bg-sky-500/10 flex items-center justify-center text-sky-400">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
              </div>
              <CardTitle className="text-lg">Upload Broker Statement</CardTitle>
              <CardDescription>
                Directly import Zerodha or Upstox PDF statements to auto-populate your holdings.
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="border-slate-800 bg-slate-900/20 hover:bg-slate-900/35 transition-colors cursor-pointer" onClick={() => router.push("/trade-log")}>
            <CardHeader className="space-y-2">
              <div className="h-10 w-10 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-400">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </div>
              <CardTitle className="text-lg">Log a Trade Manually</CardTitle>
              <CardDescription>
                Add buy/sell transactions step-by-step for custom or offline holding updates.
              </CardDescription>
            </CardHeader>
          </Card>
        </div>

        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 3v18h18" />
              <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3" />
            </svg>
          }
          title="No investment data available"
          description="You don't have a snapshot recorded yet. Upload a statement or add trades to view dashboard analytics."
          actionLabel="Go to Upload"
          actionHref="/portfolio/upload"
        />
      </div>
    );
  }

  const { 
    holdings, 
    sectorAllocation, 
    snapshotDate, 
    tradesMergedCount, 
    tradeHistory = [], 
    realizedPnlTotal = 0,
    riskStatus = { overall_risk: "MEDIUM", reasoning: "Based on guidelines and sector concentration.", flags: [] }
  } = portfolio;

  // Calculate Total valuation
  const totalValue = holdings.reduce((sum, h) => sum + (h.quantity * h.avgBuyPrice), 0);

  // Get Top 3 Holdings by valuation
  const sortedHoldings = [...holdings]
    .map(h => ({ ...h, value: h.quantity * h.avgBuyPrice }))
    .sort((a, b) => b.value - a.value);

  const topHoldings = sortedHoldings.slice(0, 3);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-50">Dashboard Overview</h1>
        <p className="text-sm text-slate-400">
          Last updated snapshot: {new Date(snapshotDate).toLocaleDateString()}
        </p>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="border-slate-800 bg-slate-900/30">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Portfolio Valuation</CardDescription>
            <CardTitle className="text-2xl font-bold text-slate-50">
              ₹{totalValue.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-slate-500">Based on last confirmed statement values</p>
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-slate-900/30">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Asset Distribution</CardDescription>
            <CardTitle className="text-2xl font-bold text-slate-50">
              {holdings.length} Active Holding{holdings.length !== 1 ? "s" : ""}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-slate-500">{tradesMergedCount} trade deltas applied since snapshot</p>
          </CardContent>
        </Card>

        <Card className="border-slate-800 bg-slate-900/30">
          <CardHeader className="pb-2">
            <CardDescription className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Overall Advisor Risk Status</CardDescription>
            <CardTitle className="text-2xl font-bold text-slate-50 flex items-center justify-between">
              {riskStatus.overall_risk === "HIGH" ? "High" : riskStatus.overall_risk === "LOW" ? "Low" : "Moderate"}
              <span className={`text-xs px-2 py-0.5 rounded border ${getRiskBadgeColor(riskStatus.overall_risk)}`}>
                {riskStatus.overall_risk} RISK
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-slate-400 leading-normal mb-1">{riskStatus.reasoning}</p>
            {riskStatus.flags && riskStatus.flags.length > 0 && (
              <div className="mt-3 pt-2.5 border-t border-slate-800/40 space-y-1.5">
                {riskStatus.flags.map((flag, idx) => (
                  <div key={idx} className="flex items-start gap-1.5 text-[10px] leading-relaxed">
                    <span className={`shrink-0 font-semibold uppercase ${
                      flag.severity === "HIGH" ? "text-red-400" : flag.severity === "MEDIUM" ? "text-amber-400" : "text-emerald-400"
                    }`}>
                      [{flag.type}]
                    </span>
                    <span className="text-slate-400">{flag.description}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Details split grid */}
      <div className="grid grid-cols-1 lg:grid-cols-10 gap-6">
        {/* Left: Top Holdings & Quick Actions */}
        <div className="lg:col-span-6 space-y-6">
          {/* Top Holdings list */}
          <Card className="border-slate-800 bg-slate-900/30">
            <CardHeader>
              <CardTitle className="text-sm font-semibold">Concentration: Top Holdings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {topHoldings.map((h) => {
                const weight = totalValue > 0 ? (h.value / totalValue) * 100 : 0;
                return (
                  <div key={h.ticker} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-200">{h.ticker} <span className="text-slate-500 font-normal">({h.name || "Stock"})</span></span>
                      <span className="font-mono text-slate-300">₹{h.value.toLocaleString("en-IN")} ({weight.toFixed(1)}%)</span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                      <div className="h-full bg-sky-500 rounded-full" style={{ width: `${weight}%` }} />
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* Quick Actions Panel */}
          <Card className="border-slate-800 bg-slate-900/30">
            <CardHeader>
              <CardTitle className="text-sm font-semibold">Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Button variant="outline" className="border-slate-800 hover:bg-slate-900" onClick={() => router.push("/portfolio/upload")}>
                Upload Statement
              </Button>
              <Button variant="outline" className="border-slate-800 hover:bg-slate-900" onClick={() => router.push("/trade-log")}>
                Add Manual Trade
              </Button>
              <Button className="bg-sky-600 hover:bg-sky-500 text-slate-50" onClick={() => router.push("/report")}>
                Run AI Advisory
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Right: Sector Allocation Summary */}
        <div className="lg:col-span-4">
          <Card className="border-slate-800 bg-slate-900/30 h-full">
            <CardHeader>
              <CardTitle className="text-sm font-semibold">Sector Exposure</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {Object.entries(sectorAllocation).length === 0 ? (
                <p className="text-xs text-slate-500 text-center py-8">No sector data available</p>
              ) : (
                Object.entries(sectorAllocation)
                  .sort((a, b) => b[1] - a[1])
                  .map(([name, weight]) => (
                    <div key={name} className="flex items-center justify-between text-xs py-1 border-b border-slate-800/40 last:border-0">
                      <span className="text-slate-300 font-medium">{name}</span>
                      <span className="font-mono text-slate-400">{Number(weight).toFixed(1)}%</span>
                    </div>
                  ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Trade History Section */}
      {tradeHistory.length > 0 && (
        <Card className="border-slate-800 bg-slate-900/30">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-sm font-semibold">Trade History (Completed)</CardTitle>
                <CardDescription className="text-xs mt-0.5">
                  {tradeHistory.length} realized trade{tradeHistory.length !== 1 ? "s" : ""}
                  {" · "}
                  Total P&L:{" "}
                  <span className={`font-mono font-semibold ${realizedPnlTotal >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {realizedPnlTotal >= 0 ? "+" : ""}₹{Number(realizedPnlTotal).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="border-slate-800">
                  <TableHead className="text-xs">Ticker</TableHead>
                  <TableHead className="text-xs">Name</TableHead>
                  <TableHead className="text-right text-xs">Qty</TableHead>
                  <TableHead className="text-right text-xs">Buy Price</TableHead>
                  <TableHead className="text-right text-xs">Sell Price</TableHead>
                  <TableHead className="text-right text-xs">P&L</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tradeHistory.map((t, i) => {
                  const pnl = t.realizedPnl || 0;
                  return (
                    <TableRow key={i} className="border-slate-800/50">
                      <TableCell className="font-medium text-slate-200 text-sm">{t.ticker}</TableCell>
                      <TableCell className="text-slate-400 text-sm">{t.name}</TableCell>
                      <TableCell className="text-right font-mono text-sm">{t.quantity}</TableCell>
                      <TableCell className="text-right font-mono text-sm">₹{Number(t.avgBuyPrice).toLocaleString("en-IN")}</TableCell>
                      <TableCell className="text-right font-mono text-sm">₹{Number(t.sellPrice).toLocaleString("en-IN")}</TableCell>
                      <TableCell className={`text-right font-mono text-sm font-semibold ${pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {pnl >= 0 ? "+" : ""}₹{Number(pnl).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function DashboardHomeSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-48 bg-slate-800" />
        <Skeleton className="h-4 w-72 bg-slate-800" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Skeleton className="h-28 bg-slate-800" />
        <Skeleton className="h-28 bg-slate-800" />
        <Skeleton className="h-28 bg-slate-800" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-10 gap-6">
        <div className="lg:col-span-6 space-y-6">
          <Skeleton className="h-48 bg-slate-800" />
          <Skeleton className="h-24 bg-slate-800" />
        </div>
        <div className="lg:col-span-4">
          <Skeleton className="h-80 bg-slate-800" />
        </div>
      </div>
    </div>
  );
}
