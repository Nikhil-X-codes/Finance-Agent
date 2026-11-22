"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const units = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 8 });
const compactDate = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeZone: "Asia/Kolkata" });
const money = (value) => Number.isFinite(value) ? inr.format(value) : "—";
const dateLabel = (value) => value && !Number.isNaN(Date.parse(value)) ? compactDate.format(new Date(value)) : "—";
const pnlColor = (value) => value > 0 ? "text-emerald-400" : value < 0 ? "text-rose-400" : "text-slate-300";
const riskLabels = { LOW: "Low", MEDIUM: "Moderate", HIGH: "High", UNAVAILABLE: "Unavailable" };
const priceSources = { STATEMENT: "Statement" };
const panel = "min-w-0 rounded-xl border border-slate-800 bg-slate-900/35";
const button = "inline-flex items-center justify-center rounded-md border border-slate-700 px-3 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800";
const primary = "inline-flex items-center justify-center rounded-md bg-slate-100 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-white";

export default function PortfolioPage() {
  const [state, setState] = useState({ loading: true });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/portfolio", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (response.status === 404) return setState({ loading: false, empty: true });
        if (!response.ok) throw new Error();
        setState({ loading: false, portfolio: await response.json() });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ loading: false, error: true });
      });
    return () => controller.abort();
  }, [attempt]);

  const { portfolio } = state;
  const holdings = [...(portfolio?.holdings || [])].sort((a, b) => b.investedCost - a.investedCost);
  const sectors = Object.entries(portfolio?.sectorAllocation || {}).sort((a, b) => b[1] - a[1]);
  const risk = portfolio?.riskStatus;
  const missingPrices = holdings.length - (portfolio?.pricedHoldingsCount ?? 0);
  const sold = [...(portfolio?.tradeHistory || [])].sort((a, b) => (b.sellDate || "").localeCompare(a.sellDate || ""));

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-semibold tracking-tight">Portfolio</h1>
          {portfolio && <p className="mt-1 text-sm text-slate-400">
            {portfolio.coverageEnd ? <>Statement dated {dateLabel(portfolio.coverageEnd)}</>
              : portfolio.snapshotDate ? <>Statement confirmed {dateLabel(portfolio.snapshotDate)}</> : "Built from logged trades"}
          </p>}
        </div>
        {!state.empty && (
          <div className="flex flex-wrap gap-2">
            <Link href="/trade-log" className={button}>Log a trade</Link>
            <Link href="/portfolio/upload" className={primary}>Import statement</Link>
          </div>
        )}
      </div>

      {state.loading && (
        <div aria-label="Loading portfolio" role="status" className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[0, 1, 2, 3].map((item) => <Skeleton key={item} className="h-24 bg-slate-800" />)}
          </div>
          <Skeleton className="h-56 bg-slate-800" />
        </div>
      )}

      {state.error && (
        <div className={panel + " p-5"} role="alert">
          <p className="text-sm text-slate-300">Your portfolio could not be loaded.</p>
          <button className={button + " mt-3"} onClick={() => { setState({ loading: true }); setAttempt((count) => count + 1); }}>Retry</button>
        </div>
      )}

      {state.empty && (
        <section className="portfolio-empty" aria-labelledby="empty-title">
          <div>
            <h2 id="empty-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">Add your first holdings</h2>
            <p className="mt-3 max-w-sm text-sm leading-relaxed text-slate-300">
              Import a broker statement to review positions before saving them, or log a trade manually.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/portfolio/upload" className={primary}>Import statement</Link>
              <Link href="/trade-log" className={button}>Log a trade</Link>
            </div>
            <p className="mt-4 text-xs text-slate-400">PDF, CSV, XLSX, or XLS</p>
          </div>
          <div className="statement-preview" aria-hidden="true">
            <div className="statement-preview-title">Broker statement</div>
            <div className="statement-preview-columns"><span>Holding</span><span>Units</span><span>Avg. cost</span></div>
            {[0, 1, 2].map((row) => (
              <div className="statement-preview-row" key={row}><span /><span /><span /></div>
            ))}
          </div>
        </section>
      )}

      {portfolio && (
        <>
          <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Metric label="Invested cost" value={portfolio.investedCost} />
            <Metric label="Market value" value={portfolio.marketValue}
              note={missingPrices > 0 ? `${missingPrices} of ${holdings.length} positions missing a price` : "From recorded prices"} />
            <Metric label="Unrealized P&L" value={portfolio.unrealizedPnl} change />
            <Metric label="Realized P&L" value={portfolio.realizedPnlTotal} change />
          </dl>

          {portfolio.invalidTrades?.length > 0 && (
            <p className="rounded-md border border-amber-800 px-4 py-3 text-sm text-amber-300">
              {portfolio.invalidTrades.length} trade entries could not be applied. <Link href="/trade-log" className="underline">Review trades</Link>
            </p>
          )}

          <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)]">
            <section className={panel} aria-labelledby="positions-heading">
              <div className="flex items-center justify-between border-b border-slate-800 px-4 py-4 sm:px-5">
                <h2 id="positions-heading" className="font-semibold">Open positions</h2>
                <span className="text-sm tabular-nums text-slate-400">{holdings.length}</span>
              </div>
              {holdings.length ? (
                <div tabIndex={0} role="region" aria-label="Open positions table" className="overflow-x-auto">
                  <table className="w-full min-w-[37rem] text-left text-sm">
                    <thead className="text-xs text-slate-400">
                      <tr><th scope="col" className="px-4 py-3">Holding</th><th scope="col" className="px-3 text-right">Units</th><th scope="col" className="px-3 text-right">Invested cost</th><th scope="col" className="px-3 text-right">Cost weight</th><th scope="col" className="px-4 text-right">Market value</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {holdings.map((holding) => (
                        <tr key={holding.isin || holding.ticker}>
                          <th scope="row" className="px-4 py-3 font-medium">
                            {holding.ticker}
                            {holding.name && holding.name !== holding.ticker && <span className="block max-w-48 truncate text-xs font-normal text-slate-400">{holding.name}</span>}
                          </th>
                          <td className="px-3 text-right tabular-nums">{units.format(holding.quantity)}</td>
                          <td className="px-3 text-right tabular-nums">{money(holding.investedCost)}</td>
                          <td className="px-3 text-right tabular-nums text-slate-400">{portfolio.investedCost > 0 ? `${(holding.investedCost / portfolio.investedCost * 100).toFixed(1)}%` : "—"}</td>
                          <td className="px-4 text-right tabular-nums">
                            {money(holding.marketValue)}
                            {holding.priceSource && <span className="block text-xs text-slate-400">{[priceSources[holding.priceSource] || holding.priceSource, holding.priceAsOf && dateLabel(holding.priceAsOf)].filter(Boolean).join(" · ")}</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="px-5 py-5 text-sm text-slate-400">There are no open positions.</p>}
            </section>

            <aside className="space-y-5">
              <section className={panel + " p-5"} aria-labelledby="sector-heading">
                <h2 id="sector-heading" className="font-semibold">Sector allocation</h2>
                {sectors.length ? (
                  <ul className="mt-4 space-y-3">
                    {sectors.map(([sector, share]) => (
                      <li key={sector}>
                        <div className="mb-1 flex justify-between gap-2 text-sm"><span>{sector}</span><span className="tabular-nums text-slate-400">{share.toFixed(1)}%</span></div>
                        <div aria-hidden="true" className="h-1 overflow-hidden rounded bg-slate-800"><div className="h-full bg-sky-500" style={{ width: Math.min(100, Math.max(0, share)) + "%" }} /></div>
                      </li>
                    ))}
                  </ul>
                ) : <p className="mt-2 text-sm text-slate-400">No allocation data available.</p>}
              </section>
              <section className={panel + " p-5"} aria-labelledby="risk-heading">
                <div className="flex items-center justify-between gap-3">
                  <h2 id="risk-heading" className="font-semibold">Concentration risk</h2>
                  <span className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300">{riskLabels[risk?.overall_risk] || "Unavailable"}</span>
                </div>
                {risk?.reasoning && <p className="mt-3 text-sm text-slate-400">{risk.reasoning}</p>}
                {risk?.flags?.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-4 text-sm text-slate-300">{risk.flags.map((flag, index) => <li key={index}>{flag.description}</li>)}</ul>}
                <Link href="/report" className="mt-4 inline-block text-sm text-sky-300 hover:underline">View reports <span aria-hidden="true">→</span></Link>
              </section>
            </aside>
          </div>

          {sold.length > 0 && (
            <section className={panel} aria-labelledby="sales-heading">
              <h2 id="sales-heading" className="border-b border-slate-800 px-5 py-4 font-semibold">Realized trades</h2>
              <div tabIndex={0} role="region" aria-label="Realized trades table" className="overflow-x-auto">
                <table className="w-full min-w-[32rem] text-left text-sm">
                  <thead className="text-xs text-slate-400"><tr><th scope="col" className="px-5 py-3">Holding</th><th scope="col" className="px-3">Date sold</th><th scope="col" className="px-3 text-right">Units sold</th><th scope="col" className="px-3 text-right">Sale price</th><th scope="col" className="px-5 text-right">Realized P&L</th></tr></thead>
                  <tbody className="divide-y divide-slate-800">
                    {sold.map((trade, index) => (
                      <tr key={index}><th scope="row" className="px-5 py-3 font-medium">{trade.ticker}</th><td className="px-3">{dateLabel(trade.sellDate)}</td><td className="px-3 text-right tabular-nums">{units.format(trade.quantity)}</td><td className="px-3 text-right tabular-nums">{money(trade.sellPrice)}</td><td className={"px-5 text-right tabular-nums " + pnlColor(trade.realizedPnl)}>{money(trade.realizedPnl)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function Metric({ label, value, note, change }) {
  return (
    <div className={panel + " px-4 py-4 sm:px-5"}>
      <dt className="text-sm text-slate-400">{label}</dt>
      <dd className={"mt-1 text-lg font-semibold tabular-nums sm:text-2xl " + (change ? pnlColor(value) : "")}>{money(value)}</dd>
      {note && <dd className="mt-1 text-xs text-slate-400">{note}</dd>}
    </div>
  );
}
