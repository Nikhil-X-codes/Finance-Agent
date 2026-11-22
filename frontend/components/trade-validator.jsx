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
      const data = await validateTradeApi({
        ticker: tradeData.ticker.toUpperCase(),
        action: tradeData.transactionType.toUpperCase(),
        quantity: Number(tradeData.quantity),
        price: Number(tradeData.price),
      });
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

    const level = (result.risk_level || (result.allowed ? "LOW" : "HIGH")).toUpperCase();
    const reasoning = result.reasoning || "Audit complete.";

    if (level === "HIGH") {
      return {
        level: "HIGH RISK",
        color: "text-red-400",
        bg: "bg-red-950/20",
        border: "border-red-900/50",
        badge: "bg-red-500/10 text-red-400 border-red-500/20",
        suggested: reasoning,
      };
    }

    if (level === "MEDIUM") {
      return {
        level: "MEDIUM RISK",
        color: "text-amber-400",
        bg: "bg-amber-950/20",
        border: "border-amber-900/50",
        badge: "bg-amber-500/10 text-amber-400 border-amber-500/20",
        suggested: reasoning,
      };
    }

    return {
      level: "LOW RISK",
      color: "text-emerald-400",
      bg: "bg-emerald-950/20",
      border: "border-emerald-900/50",
      badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
      suggested: reasoning,
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
                  {result.status === "unavailable" ? "ASSESSMENT UNAVAILABLE" : result.allowed ? "FAVORABLE ASSESSMENT" : "REVIEW REQUIRED"}
                </span>
              </div>
              
              <div className="space-y-1">
                <span className="text-[10px] text-slate-500 font-semibold block uppercase">AI Advice & Analysis</span>
                <p className="text-slate-350 font-medium leading-relaxed">{risk.suggested}</p>
              </div>

              {result.portfolio_impact && (
                <div className="space-y-1 pt-1">
                  <span className="text-[10px] text-slate-500 font-semibold block uppercase">Portfolio Impact</span>
                  <p className="text-slate-350 leading-relaxed font-medium">{result.portfolio_impact}</p>
                </div>
              )}

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
          disabled={loading || !result || result.status === "blocked"}
          className="text-xs px-4 bg-sky-600 hover:bg-sky-500 text-slate-50"
        >
          Proceed
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
