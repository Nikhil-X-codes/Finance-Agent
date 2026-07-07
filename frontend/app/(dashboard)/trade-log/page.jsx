"use client";

import { useState, useEffect, useCallback } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import TradeValidator from "@/components/trade-validator";

const tradeFormSchema = z.object({
  ticker: z.string().min(1, "Ticker is required"),
  transactionType: z.enum(["BUY", "SELL"], { required_error: "Select BUY or SELL" }),
  quantity: z.coerce.number().positive("Must be positive"),
  price: z.coerce.number().positive("Must be positive"),
  date: z.string().min(1, "Date is required"),
});

export default function TradeLogPage() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deleteId, setDeleteId] = useState(null);
  const [error, setError] = useState(null);

  // Trade validator state variables
  const [showValidator, setShowValidator] = useState(false);
  const [proposedTrade, setProposedTrade] = useState(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(tradeFormSchema),
    defaultValues: {
      ticker: "",
      transactionType: "BUY",
      quantity: "",
      price: "",
      date: new Date().toISOString().split("T")[0],
    },
  });

  const fetchTrades = useCallback(async () => {
    try {
      const res = await fetch("/api/trades");
      if (!res.ok) throw new Error("Failed to fetch trades");
      const data = await res.json();
      setTrades(data.trades || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades]);

  const onSubmitForm = (data) => {
    setProposedTrade(data);
    setShowValidator(true);
  };

  const executeTrade = async (trade) => {
    const tradeData = trade || proposedTrade;
    if (!tradeData) return;
    setSubmitting(true);
    setError(null);

    try {
      const res = await fetch("/api/trades", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(tradeData),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || "Failed to add trade");
      }

      const newTrade = await res.json();
      setTrades((prev) => [newTrade, ...prev]);
      reset();
      setProposedTrade(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (tradeId) => {
    setDeleteId(tradeId);
    try {
      const res = await fetch(`/api/trades/${tradeId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to delete trade");
      setTrades((prev) => prev.filter((t) => t.id !== tradeId));
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleteId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Trade Log</h1>
        <p className="mt-1 text-sm text-slate-400">
          Manually log buy/sell trades to keep your portfolio up to date between statement uploads.
        </p>
      </div>

      {/* Add trade form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add Trade</CardTitle>
          <CardDescription>
            Enter trade details. Ticker is validated against known NSE symbols.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmitForm)} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
              {/* Ticker */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-400">Ticker</label>
                <Input
                  placeholder="e.g. RELIANCE"
                  {...register("ticker")}
                  className={errors.ticker ? "border-red-700" : ""}
                />
                {errors.ticker && (
                  <p className="text-xs text-red-400">{errors.ticker.message}</p>
                )}
              </div>

              {/* Transaction Type */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-400">Type</label>
                <Select
                  {...register("transactionType")}
                  className={errors.transactionType ? "border-red-700" : ""}
                >
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </Select>
                {errors.transactionType && (
                  <p className="text-xs text-red-400">{errors.transactionType.message}</p>
                )}
              </div>

              {/* Quantity */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-400">Quantity</label>
                <Input
                  type="number"
                  step="0.01"
                  placeholder="10"
                  {...register("quantity")}
                  className={errors.quantity ? "border-red-700" : ""}
                />
                {errors.quantity && (
                  <p className="text-xs text-red-400">{errors.quantity.message}</p>
                )}
              </div>

              {/* Price */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-400">Price (₹)</label>
                <Input
                  type="number"
                  step="0.01"
                  placeholder="2500.00"
                  {...register("price")}
                  className={errors.price ? "border-red-700" : ""}
                />
                {errors.price && (
                  <p className="text-xs text-red-400">{errors.price.message}</p>
                )}
              </div>

              {/* Date */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-400">Date</label>
                <Input
                  type="date"
                  {...register("date")}
                  className={errors.date ? "border-red-700" : ""}
                />
                {errors.date && (
                  <p className="text-xs text-red-400">{errors.date.message}</p>
                )}
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="rounded-lg border border-red-900/50 bg-red-950/20 px-4 py-3 text-sm text-red-400">
                {error}
              </div>
            )}

            <div className="flex justify-end">
              <Button type="submit" disabled={submitting}>
                {submitting ? "Adding..." : "Add Trade"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Trade history */}
      {loading ? (
        <TradeLogSkeleton />
      ) : trades.length === 0 ? (
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
              <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
            </svg>
          }
          title="No trades yet"
          description="Add your first trade above to start tracking buy/sell activity."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Trade History ({trades.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Ticker</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="w-16" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {trades.map((trade) => (
                  <TableRow key={trade.id}>
                    <TableCell className="text-slate-400">
                      {trade.date}
                    </TableCell>
                    <TableCell className="font-medium text-slate-200">
                      {trade.ticker}
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          trade.transactionType === "BUY"
                            ? "bg-emerald-950/50 text-emerald-400 ring-1 ring-emerald-800"
                            : "bg-red-950/50 text-red-400 ring-1 ring-red-800"
                        }`}
                      >
                        {trade.transactionType}
                      </span>
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {trade.quantity}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      ₹{Number(trade.price).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </TableCell>
                    <TableCell>
                      <button
                        onClick={() => handleDelete(trade.id)}
                        disabled={deleteId === trade.id}
                        className="rounded p-1 text-slate-500 hover:bg-red-950/50 hover:text-red-400 transition-colors disabled:opacity-50"
                        title="Delete trade"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
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

      <TradeValidator
        open={showValidator}
        onClose={() => {
          setShowValidator(false);
          setProposedTrade(null);
        }}
        tradeData={proposedTrade}
        onConfirm={executeTrade}
      />
    </div>
  );
}

function TradeLogSkeleton() {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3">
      <Skeleton className="h-5 w-32" />
      {[...Array(4)].map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}
