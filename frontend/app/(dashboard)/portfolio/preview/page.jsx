"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";

export default function PreviewPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const previewId = searchParams.get("id");

  const [holdings, setHoldings] = useState([]);
  const [tradeHistory, setTradeHistory] = useState([]);
  const [summary, setSummary] = useState(null);
  const [brokerDetected, setBrokerDetected] = useState("");
  const [parseConfidence, setParseConfidence] = useState(0);
  const [unrecognizedRows, setUnrecognizedRows] = useState([]);
  const [editingCell, setEditingCell] = useState(null); // { section: 'holdings'|'trades', rowIndex, field }
  const [editValue, setEditValue] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    // Load preview data from sessionStorage
    const raw = sessionStorage.getItem("uploadPreview");
    if (raw) {
      try {
        const data = JSON.parse(raw);
        setHoldings(data.holdings || []);
        setTradeHistory(data.tradeHistory || []);
        setSummary(data.summary || null);
        setBrokerDetected(data.brokerDetected || "Unknown");
        setParseConfidence(data.parseConfidence || 0);
        setUnrecognizedRows(data.unrecognizedRows || []);
      } catch {
        setError("Failed to load preview data");
      }
    }
    setLoaded(true);
  }, []);

  const startEdit = (section, rowIndex, field, currentValue) => {
    setEditingCell({ section, rowIndex, field });
    setEditValue(String(currentValue));
  };

  const saveEdit = () => {
    if (!editingCell) return;
    const { section, rowIndex, field } = editingCell;

    if (section === "holdings") {
      setHoldings((prev) => {
        const updated = [...prev];
        const row = { ...updated[rowIndex] };
        if (field === "quantity" || field === "avgBuyPrice" || field === "currentPrice") {
          const num = parseFloat(editValue);
          if (!isNaN(num) && num >= 0) {
            row[field] = num;
          }
        } else {
          row[field] = editValue;
        }
        updated[rowIndex] = row;
        return updated;
      });
    } else {
      setTradeHistory((prev) => {
        const updated = [...prev];
        const row = { ...updated[rowIndex] };
        if (field === "quantity" || field === "avgBuyPrice" || field === "sellPrice" || field === "realizedPnl") {
          const num = parseFloat(editValue);
          if (!isNaN(num)) {
            row[field] = num;
          }
        } else {
          row[field] = editValue;
        }
        updated[rowIndex] = row;
        return updated;
      });
    }

    setEditingCell(null);
    setEditValue("");
  };

  const cancelEdit = () => {
    setEditingCell(null);
    setEditValue("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") saveEdit();
    if (e.key === "Escape") cancelEdit();
  };

  const removeRow = (section, index) => {
    if (section === "holdings") {
      setHoldings((prev) => prev.filter((_, i) => i !== index));
    } else {
      setTradeHistory((prev) => prev.filter((_, i) => i !== index));
    }
  };

  const handleConfirm = async () => {
    if (holdings.length === 0 && tradeHistory.length === 0) return;

    setConfirming(true);
    setError(null);

    // Combine holdings and trade history for statement snapshots
    const combined = [
      ...holdings.map((h) => ({ ...h, status: "UNREALIZED" })),
      ...tradeHistory.map((t) => ({ ...t, status: "REALIZED" })),
    ];

    try {
      const res = await fetch("/api/statements/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ previewId: previewId || "manual", holdings: combined }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Confirmation failed");
      }

      // Clean up
      sessionStorage.removeItem("uploadPreview");
      router.push("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setConfirming(false);
    }
  };

  if (!loaded) {
    return <PreviewSkeleton />;
  }

  const hasData = holdings.length > 0 || tradeHistory.length > 0;

  if (!hasData && loaded) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Preview Statement</h1>
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          }
          title="No data to preview"
          description="Upload a broker statement first to see your parsed portfolio data here."
          actionLabel="Upload Statement"
          actionHref="/portfolio/upload"
        />
      </div>
    );
  }

  const holdingFields = ["ticker", "name", "quantity", "avgBuyPrice", "currentPrice"];
  const tradeFields = ["ticker", "name", "quantity", "avgBuyPrice", "sellPrice", "realizedPnl"];

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight font-sans text-slate-100">Review & Confirm Portfolio</h1>
          <p className="mt-1 text-sm text-slate-400">
            Broker detected: <span className="text-slate-300 font-medium">{brokerDetected}</span>
            {" · "}
            Confidence: <span className={parseConfidence >= 0.8 ? "text-emerald-400 font-semibold" : "text-amber-400 font-semibold"}>
              {Math.round(parseConfidence * 100)}%
            </span>
          </p>
        </div>
      </div>

      {/* Summary Card */}
      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card className="bg-slate-900/40 border-slate-800">
            <CardHeader className="py-3">
              <CardDescription className="text-xs">Realized gains / loss</CardDescription>
              <CardTitle className={`text-lg font-mono ${summary.realized_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                ₹{Number(summary.realized_pnl).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card className="bg-slate-900/40 border-slate-800">
            <CardHeader className="py-3">
              <CardDescription className="text-xs">Unrealized gains / loss</CardDescription>
              <CardTitle className={`text-lg font-mono ${summary.unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                ₹{Number(summary.unrealized_pnl).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card className="bg-slate-900/40 border-slate-800">
            <CardHeader className="py-3">
              <CardDescription className="text-xs">Total charges & taxes</CardDescription>
              <CardTitle className="text-lg font-mono text-slate-300">
                ₹{Number(summary.total_charges || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
              </CardTitle>
            </CardHeader>
          </Card>
        </div>
      )}

      {/* Unrecognized rows warning */}
      {unrecognizedRows.length > 0 && (
        <div className="rounded-lg border border-amber-900/50 bg-amber-950/20 px-4 py-3">
          <p className="text-sm font-medium text-amber-400">
            {unrecognizedRows.length} row{unrecognizedRows.length !== 1 ? "s" : ""} skipped during parsing
          </p>
          <ul className="mt-2 space-y-1">
            {unrecognizedRows.map((row, i) => (
              <li key={i} className="text-xs text-amber-500/80">
                Row {i+1}: {row.reason || "Error decoding row values"}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Active holdings table */}
      <Card className="bg-slate-900/20 border-slate-800">
        <CardHeader>
          <CardTitle className="text-base text-slate-200">
            Current Holdings (Unrealized) — {holdings.length} Positions
          </CardTitle>
          <CardDescription>
            These are stocks/mutual funds you currently hold. Click any cell to edit.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-slate-800">
                <TableHead>Ticker</TableHead>
                <TableHead>Name</TableHead>
                <TableHead className="text-right">Quantity</TableHead>
                <TableHead className="text-right">Avg Buy Price</TableHead>
                <TableHead className="text-right">Current Price</TableHead>
                <TableHead>Sector</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {holdings.map((h, rowIndex) => (
                <TableRow key={rowIndex} className="border-slate-800/50 hover:bg-slate-900/20">
                  {holdingFields.map((field) => {
                    const isEditing =
                      editingCell?.section === "holdings" &&
                      editingCell?.rowIndex === rowIndex &&
                      editingCell?.field === field;
                    const isNumeric = ["quantity", "avgBuyPrice", "currentPrice"].includes(field);
                    const value = h[field];

                    return (
                      <TableCell
                        key={field}
                        className={`${isNumeric ? "text-right font-mono" : ""} cursor-pointer`}
                        onClick={() => !isEditing && startEdit("holdings", rowIndex, field, value)}
                      >
                        {isEditing ? (
                          <Input
                            type={isNumeric ? "number" : "text"}
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onBlur={saveEdit}
                            onKeyDown={handleKeyDown}
                            autoFocus
                            className="h-7 w-full border-sky-500 bg-slate-950 text-sm"
                            step={isNumeric ? "0.01" : undefined}
                          />
                        ) : (
                          <span className="hover:text-sky-400 transition-colors">
                            {isNumeric && ["avgBuyPrice", "currentPrice"].includes(field)
                              ? `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`
                              : value ?? "—"}
                          </span>
                        )}
                      </TableCell>
                    );
                  })}
                  <TableCell className="text-slate-400 text-sm">{h.sector || "—"}</TableCell>
                  <TableCell>
                    <button
                      onClick={() => removeRow("holdings", rowIndex)}
                      className="rounded p-1 text-slate-500 hover:bg-red-950/50 hover:text-red-400 transition-colors"
                      title="Remove row"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Trade history table */}
      {tradeHistory.length > 0 && (
        <Card className="bg-slate-900/20 border-slate-800">
          <CardHeader>
            <CardTitle className="text-base text-slate-200">
              Trade History (Realized/Sold) — {tradeHistory.length} Trades
            </CardTitle>
            <CardDescription>
              Completed trades present in the statement. Click any cell to edit.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="border-slate-800">
                  <TableHead>Ticker</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Avg Buy Price</TableHead>
                  <TableHead className="text-right">Sell Price</TableHead>
                  <TableHead className="text-right">Realized P&L</TableHead>
                  <TableHead className="w-16" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {tradeHistory.map((t, rowIndex) => (
                  <TableRow key={rowIndex} className="border-slate-800/50 hover:bg-slate-900/20">
                    {tradeFields.map((field) => {
                      const isEditing =
                        editingCell?.section === "trades" &&
                        editingCell?.rowIndex === rowIndex &&
                        editingCell?.field === field;
                      const isNumeric = ["quantity", "avgBuyPrice", "sellPrice", "realizedPnl"].includes(field);
                      const value = t[field];

                      return (
                        <TableCell
                          key={field}
                          className={`${isNumeric ? "text-right font-mono" : ""} cursor-pointer`}
                          onClick={() => !isEditing && startEdit("trades", rowIndex, field, value)}
                        >
                          {isEditing ? (
                            <Input
                              type={isNumeric ? "number" : "text"}
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onBlur={saveEdit}
                              onKeyDown={handleKeyDown}
                              autoFocus
                              className="h-7 w-full border-sky-500 bg-slate-950 text-sm"
                              step={isNumeric ? "0.01" : undefined}
                            />
                          ) : (
                            <span className={`hover:text-sky-400 transition-colors ${field === "realizedPnl" ? (value >= 0 ? "text-emerald-400" : "text-red-400") : ""}`}>
                              {isNumeric && ["avgBuyPrice", "sellPrice", "realizedPnl"].includes(field)
                                ? `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`
                                : value ?? "—"}
                            </span>
                          )}
                        </TableCell>
                      );
                    })}
                    <TableCell>
                      <button
                        onClick={() => removeRow("trades", rowIndex)}
                        className="rounded p-1 text-slate-500 hover:bg-red-950/50 hover:text-red-400 transition-colors"
                        title="Remove row"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/20 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-end gap-2">
        <a href="/portfolio/upload">
          <Button variant="secondary">Cancel</Button>
        </a>
        <Button onClick={handleConfirm} disabled={confirming || (!holdings.length && !tradeHistory.length)}>
          {confirming ? "Saving..." : `Confirm Portfolio`}
        </Button>
      </div>
    </div>
  );
}

function PreviewSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-48" />
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3">
        <Skeleton className="h-5 w-36" />
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
      <div className="flex justify-end gap-2">
        <Skeleton className="h-9 w-20" />
        <Skeleton className="h-9 w-40" />
      </div>
    </div>
  );
}
