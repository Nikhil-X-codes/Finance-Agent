"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getPopularStocks, searchStocks } from "@/lib/api";

const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
const timestamp = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata",
});
const quoteLabels = { delayed: "Delayed quote", last_published: "Last published quote", stale_cache: "Stale quote" };
const control = "rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50";

export default function StocksPage() {
  const [popular, setPopular] = useState({ loading: true });
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState(null);
  const activeSearch = useRef(null);

  function loadPopular(signal) {
    setPopular((previous) => ({ ...previous, loading: true, error: false }));
    getPopularStocks(signal)
      .then((data) => setPopular({ rows: data.stocks || [], loading: false, disabled: data.status === "disabled" }))
      .catch(() => {
        if (!signal?.aborted) setPopular((previous) => ({ ...previous, loading: false, error: true }));
      });
  }

  useEffect(() => {
    const controller = new AbortController();
    loadPopular(controller.signal);
    return () => {
      controller.abort();
      activeSearch.current?.abort();
    };
  }, []);

  async function submit(event) {
    event.preventDefault();
    const query = draft.trim();
    if (!query) return;
    activeSearch.current?.abort();
    const controller = new AbortController();
    activeSearch.current = controller;
    setSearch({ query, loading: true });

    try {
      const data = await searchStocks(query, controller.signal);
      if (!controller.signal.aborted) {
        setSearch({ query, rows: data.results || [], disabled: data.status === "disabled" });
      }
    } catch {
      if (!controller.signal.aborted) setSearch({ query, error: true });
    }
  }

  function clearSearch() {
    activeSearch.current?.abort();
    setDraft("");
    setSearch(null);
  }

  return (
    <div className="space-y-7">
      <h1 className="text-3xl font-semibold tracking-tight">Stocks</h1>
      <form onSubmit={submit} className="max-w-xl space-y-2">
        <label htmlFor="stock-query" className="block text-sm font-medium">NSE ticker</label>
        <div className="flex gap-2">
          <input id="stock-query" value={draft} maxLength={100} onChange={(event) => setDraft(event.target.value)} disabled={popular.disabled}
            placeholder="e.g. TCS" className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-900/40 px-3 py-2 text-sm" />
          <button type="submit" disabled={popular.disabled || !draft.trim()} className="rounded-md bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-white disabled:opacity-50">Search</button>
        </div>
      </form>

      {search ? (
        <section aria-labelledby="search-heading" className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h2 id="search-heading" className="min-w-0 break-words text-lg font-semibold">Results for “{search.query}”</h2>
            <button type="button" className={control + " shrink-0"} onClick={clearSearch}>Clear search</button>
          </div>
          {search.loading && <p role="status" className="text-sm text-slate-400">Searching…</p>}
          {search.error && <p role="alert" className="text-sm text-amber-300">Search is temporarily unavailable. Try again.</p>}
          {search.disabled && <p role="status" className="text-sm text-slate-400">Market data is disabled for this deployment.</p>}
          {!search.disabled && search.rows?.length === 0 && <p role="status" className="text-sm text-slate-400">No matching NSE tickers.</p>}
          {search.rows?.length > 0 && <StockTable stocks={search.rows} />}
        </section>
      ) : (
        <section aria-labelledby="popular-heading" className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h2 id="popular-heading" className="text-lg font-semibold">Market movers</h2>
            <button type="button" className={control} onClick={() => loadPopular()} disabled={popular.loading}>Refresh</button>
          </div>
          {popular.loading && <p role="status" className="text-sm text-slate-400">Loading quotes…</p>}
          {popular.error && <p role="alert" className="text-sm text-amber-300">{popular.rows?.length ? "Refresh failed. Showing the previously loaded quotes." : "Quotes could not be loaded."}</p>}
          {["gainers", "losers"].map((direction) => {
            const rows = popular.rows?.filter((stock) => stock.moverType === direction) || [];
            return rows.length > 0 && (
              <div key={direction} className="space-y-2">
                <h3 className="text-sm font-medium text-slate-300">{direction === "gainers" ? "Top gainers" : "Top losers"}</h3>
                <StockTable stocks={rows} />
              </div>
            );
          })}
          {popular.disabled && !popular.loading && <p role="status" className="text-sm text-slate-400">Market data is disabled for this deployment.</p>}
          {!popular.disabled && popular.rows?.length === 0 && !popular.loading && !popular.error && <p className="text-sm text-slate-400">No market movers available.</p>}
        </section>
      )}
    </div>
  );
}

function StockTable({ stocks }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/35" tabIndex={0} role="region" aria-label="Stock quotes">
      <table className="w-full min-w-[32rem] text-left text-sm">
        <thead className="border-b border-slate-800 text-xs text-slate-400">
          <tr>
            <th scope="col" className="px-4 py-3">Company</th>
            <th scope="col" className="px-4 py-3 text-right">Price</th>
            <th scope="col" className="px-4 py-3 text-right">Day change</th>
            <th scope="col" className="px-4 py-3">Quote source · IST</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {stocks.map((stock) => {
            const hasPrice = Number.isFinite(stock.price);
            const hasChange = hasPrice && Number.isFinite(stock.changePercent);
            const quoteLabel = quoteLabels[stock.quoteStatus] || (!stock.quoteStatus && stock.fresh === false ? "Stale quote" : null);
            const sign = stock.changePercent > 0 ? "+" : "";
            const changeClass = stock.changePercent > 0 ? "text-emerald-400" : stock.changePercent < 0 ? "text-rose-400" : "text-slate-400";
            const publishedAt = stock.marketTimestamp && !Number.isNaN(Date.parse(stock.marketTimestamp))
              ? timestamp.format(new Date(stock.marketTimestamp))
              : "Timestamp unavailable";

            return (
              <tr key={stock.symbol}>
                <th scope="row" className="px-4 py-3 font-medium">
                  <Link href={"/stocks/" + encodeURIComponent(stock.symbol)} className="text-sky-300 hover:underline">{stock.symbol}</Link>
                  {stock.name && stock.name !== stock.symbol && <span className="mt-0.5 block text-xs font-normal text-slate-400">{stock.name}</span>}
                </th>
                <td className="px-4 text-right tabular-nums">{hasPrice ? currency.format(stock.price) : <span className="text-xs text-slate-400">Unavailable</span>}</td>
                <td className={"px-4 text-right tabular-nums " + changeClass}>{hasChange ? sign + stock.changePercent.toFixed(2) + "%" : "—"}</td>
                <td className="px-4 text-xs text-slate-400">
                  {hasPrice ? <>{stock.source && <span className="block text-slate-300">{stock.source}</span>}
                    {publishedAt}{quoteLabel && <span className="block text-slate-300">{quoteLabel}</span>}</> : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
