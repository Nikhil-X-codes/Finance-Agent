"use client";

import { useState, useEffect } from "react";
import { Dialog, DialogHeader, DialogTitle, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { validateTrade as validateTradeApi } from "@/lib/api";

export default function TradeValidator({ open, onClose, tradeData, onConfirm }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open && tradeData) {
      validateTrade();
    } else {
      setResult(null);
      setError(null);
    }
  }, [open, tradeData]);

  const validateTrade = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      // 1. Get user id from session API
      const userRes = await fetch("/api/auth/me");
      if (!userRes.ok) throw new Error("Please log in to validate trades.");
      const userData = await userRes.json();
      const userId = userData.userId;

      // 2. Get current portfolio holdings from portfolio API
      const portRes = await fetch("/api/portfolio");
      let portfolioHoldings = [];
      if (portRes.ok) {
        const portData = await portRes.json();
        // Map keys to match backend's Holding model (avgBuyPrice -> avg_buy_price, assetType -> asset_type)
        portfolioHoldings = (portData.holdings || []).map(h => ({
          isin: h.isin || "INE000000000",
          ticker: h.ticker || "",
          name: h.name || h.ticker || "",
          quantity: Number(h.quantity),
          avg_buy_price: Number(h.avgBuyPrice),
          asset_type: h.assetType === "MUTUAL_FUND" ? "MUTUAL_FUND" : "STOCK",
          sector: h.sector || "Other"
        }));
      }

      // 3. Pre-flight insufficient quantity sell check (local audit)
      const actionUpper = tradeData.transactionType.toUpperCase();
      const qty = Number(tradeData.quantity);
      if (actionUpper === "SELL" || actionUpper === "TRIM" || actionUpper === "EXIT") {
        const holding = portfolioHoldings.find(
          (h) => h.ticker.toUpperCase() === tradeData.ticker.toUpperCase()
        );
        if (!holding || holding.quantity < qty) {
          setResult({
            allowed: false,
            ticker: tradeData.ticker.toUpperCase(),
            action: actionUpper,
            quantity: qty,
            price: Number(tradeData.price),
            new_portfolio_weight: 0,
            limit_threshold: 0,
            warnings: [
              `Insufficient quantity to execute ${actionUpper}. You currently hold ${
                holding ? holding.quantity : 0
              } shares of ${tradeData.ticker.toUpperCase()} but attempted to sell/trim ${qty} shares.`,
            ],
            citations: ["Local Holdings Audit"],
          });
          setLoading(false);
          return;
        }
      }

      // 4. Call client-side API helper which POSTs directly to FastAPI
      const proposedTradeData = {
        ticker: tradeData.ticker.toUpperCase(),
        action: actionUpper,
        quantity: qty,
        price: Number(tradeData.price)
      };

      const data = await validateTradeApi(userId, proposedTradeData, portfolioHoldings);
      setResult(data);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  // Compute risk level and suggested action details
  const getRiskDetails = () => {
    if (!result) return { level: "UNKNOWN", color: "text-slate-400", bg: "bg-slate-900", border: "border-slate-800" };

    const allowed = result.allowed;
    const warnings = result.warnings || [];

    if (!allowed) {
      return {
        level: "HIGH RISK",
        color: "text-red-400",
        bg: "bg-red-950/20",
        border: "border-red-900/50",
        badge: "bg-red-500/10 text-red-400 border-red-500/20",
        suggested: "Do not execute. Trade violates concentration limits or holdings are insufficient.",
      };
    }

    if (warnings.length > 0) {
      return {
        level: "MEDIUM RISK",
        color: "text-amber-400",
        bg: "bg-amber-950/20",
        border: "border-amber-900/50",
        badge: "bg-amber-500/10 text-amber-400 border-amber-500/20",
        suggested: "Proceed with caution. The trade is within legal limits, but approaches exposure thresholds.",
      };
    }

    return {
      level: "LOW RISK",
      color: "text-emerald-400",
      bg: "bg-emerald-950/20",
      border: "border-emerald-900/50",
      badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
      suggested: "Compliant trade. Action is aligned with concentration guidelines.",
    };
  };

  const risk = getRiskDetails();

  return (
    <Dialog open={open} onClose={onClose} className="max-w-md">
      <DialogHeader>
        <DialogTitle className="text-base text-slate-100 font-semibold flex items-center justify-between">
          <span>AI Compliance Audit</span>
          {result && (
            <span className={`text-[10px] px-2 py-0.5 rounded border font-semibold font-mono ${risk.badge}`}>
              {risk.level}
            </span>
          )}
        </DialogTitle>
      </DialogHeader>

      <DialogContent className="space-y-4">
        {loading ? (
          <div className="py-8 flex flex-col items-center justify-center space-y-3 text-slate-400">
            <svg className="animate-spin text-sky-400" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
            </svg>
            <span className="text-xs animate-pulse text-slate-400 font-medium">Auditing trade against regulations...</span>
          </div>
        ) : error ? (
          <div className="rounded-lg border border-red-950 bg-red-950/20 p-4 text-xs text-red-400 leading-relaxed">
            <strong>Audit Error:</strong> {error}
          </div>
        ) : result ? (
          <div className="space-y-4">
            {/* Audit Status Card */}
            <div className={`p-4 rounded-xl border text-xs space-y-3 ${risk.bg} ${risk.border}`}>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-300 uppercase tracking-wider">Validation Status</span>
                <span className={`font-bold ${result.allowed ? "text-emerald-400" : "text-red-400"}`}>
                  {result.allowed ? "VALID (COMPLIANT)" : "INVALID (NON-COMPLIANT)"}
                </span>
              </div>
              
              <div className="space-y-1">
                <span className="text-[10px] text-slate-500 font-semibold block uppercase">Suggested Action</span>
                <p className="text-slate-350 font-medium leading-relaxed">{risk.suggested}</p>
              </div>

              {result.new_portfolio_weight !== undefined && (
                <div className="grid grid-cols-2 gap-4 pt-2 border-t border-slate-800/40 text-[10px] text-slate-500 font-mono">
                  <div>
                    <span>Simulated Weight: </span>
                    <strong className="text-slate-300 block text-xs mt-0.5">{Number(result.new_portfolio_weight).toFixed(1)}%</strong>
                  </div>
                  {result.limit_threshold > 0 && (
                    <div>
                      <span>Limit Threshold: </span>
                      <strong className="text-slate-300 block text-xs mt-0.5">{Number(result.limit_threshold).toFixed(1)}%</strong>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Warnings Alert */}
            {result.warnings && result.warnings.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Compliance Warnings</p>
                <div className="rounded-lg border border-amber-900/40 bg-amber-950/10 p-3.5 space-y-2">
                  {result.warnings.map((warn, i) => (
                    <p key={i} className="text-xs text-amber-400 leading-normal flex items-start gap-2">
                      <span className="mt-0.5 shrink-0 select-none text-[10px]">⚠️</span>
                      <span>{warn}</span>
                    </p>
                  ))}
                </div>
              </div>
            )}

            {/* Citations List */}
            {result.citations && result.citations.length > 0 && (
              <div className="space-y-1">
                <p className="text-[9px] uppercase font-bold text-slate-500 tracking-wider">Audited Guidelines Sources</p>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {result.citations.map((cite, i) => (
                    <span key={i} className="text-[9px] bg-slate-950 text-slate-400 px-2 py-0.5 rounded border border-slate-850 font-medium">
                      {cite}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </DialogContent>

      <DialogFooter>
        <Button variant="secondary" onClick={onClose} disabled={loading} className="text-xs px-4">
          Cancel
        </Button>
        <Button
          onClick={() => {
            onConfirm(tradeData);
            onClose();
          }}
          disabled={loading || !result || !result.allowed}
          className="text-xs px-4 bg-sky-600 hover:bg-sky-500 text-slate-50"
        >
          Proceed
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
