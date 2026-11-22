"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { getFundCategories, getFundComparison } from "@/lib/api";

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 4 });

export default function FundsPage() {
  const [categories, setCategories] = useState([]);
  const [activeCategory, setActiveCategory] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [categoryAttempt, setCategoryAttempt] = useState(0);
  const activeComparison = useRef(null);

  // Sorting state
  const [sortField, setSortField] = useState("1Y"); // default sort by 1Y CAGR
  const [sortDirection, setSortDirection] = useState("desc");

  // Fetch categories on mount
  useEffect(() => {
    const controller = new AbortController();
    const fetchCategories = async () => {
      setCategoriesLoading(true);
      setError(null);
      try {
        const json = await getFundCategories(controller.signal);
        if (controller.signal.aborted) return;
        const cats = json.categories || [];
        setCategories(cats);
        
        if (cats.length > 0) {
          // Default selection: Auto-select "Large Cap" if it exists, otherwise select the first category
          if (cats.includes("Large Cap")) {
            setActiveCategory("Large Cap");
          } else {
            setActiveCategory(cats[0]);
          }
        } else {
          setLoading(false);
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setLoading(false);
          setError(err.message);
        }
      } finally {
        if (!controller.signal.aborted) setCategoriesLoading(false);
      }
    };
    fetchCategories();
    return () => controller.abort();
  }, [categoryAttempt]);

  const fetchComparison = useCallback(async (category, forceRefresh = false) => {
    activeComparison.current?.abort();
    const controller = new AbortController();
    activeComparison.current = controller;
    setRefreshing(forceRefresh);
    if (forceRefresh) {
      setLoading(false);
    } else {
      setLoading(true);
      setData(null);
    }
    setError(null);
    try {
      const json = await getFundComparison(category, forceRefresh, controller.signal);
      if (!controller.signal.aborted) setData(json);
    } catch (err) {
      if (!controller.signal.aborted) setError(err.message);
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    if (activeCategory) {
      fetchComparison(activeCategory);
    }
    return () => activeComparison.current?.abort();
  }, [activeCategory, fetchComparison]);

  const handleRefresh = () => {
    if (activeCategory) {
      fetchComparison(activeCategory, true);
    } else {
      setCategoryAttempt((count) => count + 1);
    }
  };

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection(prev => prev === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  const formatPercent = (val) => {
    if (val === undefined || val === null) return "-";
    const num = Number(val);
    if (isNaN(num)) return "-";
    return `${num.toFixed(2)}%`;
  };

  const formatNumber = (val) => {
    if (val === undefined || val === null) return "-";
    const num = Number(val);
    if (isNaN(num)) return "-";
    return num.toFixed(2);
  };

  // Safe client-side sorting logic
  const getSortedFunds = () => {
    if (!data?.funds) return [];
    const fundsCopy = [...data.funds];
    if (!sortField) return fundsCopy;

    return fundsCopy.sort((a, b) => {
      let valA, valB;
      if (sortField === "1Y" || sortField === "3Y" || sortField === "5Y") {
        valA = a.cagr?.[sortField];
        valB = b.cagr?.[sortField];
      } else if (sortField === "sharpe") {
        valA = a.risk?.sharpe;
        valB = b.risk?.sharpe;
      }

      const numA = valA !== null && valA !== undefined ? Number(valA) : -Infinity;
      const numB = valB !== null && valB !== undefined ? Number(valB) : -Infinity;

      if (sortDirection === "asc") {
        return numA - numB;
      } else {
        return numB - numA;
      }
    });
  };

  const renderSortIndicator = (field) => {
    if (sortField !== field) return null;
    return sortDirection === "asc" ? " ↑" : " ↓";
  };

  const renderCagrCell = (val) => {
    if (val === undefined || val === null) {
      return <TableCell className="text-right font-mono text-slate-500">-</TableCell>;
    }
    const numVal = Number(val);
    const isPositive = numVal > 0;
    const isNegative = numVal < 0;
    const textClass = isPositive ? "text-emerald-400" : isNegative ? "text-rose-400" : "text-slate-300";
    return (
      <TableCell className={`text-right font-mono ${textClass}`}>
        {formatPercent(val)}
      </TableCell>
    );
  };

  const sortedFunds = getSortedFunds();

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-50">Mutual Fund Explorer</h1>
          <p className="text-sm text-slate-400">
            Compare rolling returns, CAGR performance, risk ratios, and valuation metrics by category.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {data?.dataAsOf && (
            <span className="text-xs text-slate-500">
              Data as of: {data.dataAsOf}
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={categoriesLoading || loading || refreshing}
            className="border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800 hover:text-slate-50"
          >
            {refreshing ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                </svg>
                Refreshing...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                </svg>
                Refresh Data
              </span>
            )}
          </Button>
        </div>
      </div>

      {/* Category Tabs */}
      {categoriesLoading ? (
        <div className="flex gap-2 rounded-xl border border-slate-800/80 bg-slate-900/50 p-2">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-9 w-24 bg-slate-800" />
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2 rounded-xl border border-slate-800/80 bg-slate-900/50 p-2 backdrop-blur-sm">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition-all ${
                activeCategory === cat
                  ? "bg-slate-800 text-slate-50 shadow-md ring-1 ring-slate-700/50"
                  : "text-slate-400 hover:bg-slate-800/30 hover:text-slate-200"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      )}

      {/* Comparison Grid & Table */}
      {error ? (
        <div className="rounded-xl border border-red-900/50 bg-red-950/20 p-6 text-center text-red-400">
          {error}
        </div>
      ) : loading ? (
        <FundsTableSkeleton />
      ) : !sortedFunds || sortedFunds.length === 0 ? (
        <Card className="border-slate-800 bg-slate-900/40">
          <CardContent className="flex flex-col items-center justify-center py-12 text-slate-500">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <h3 className="mt-4 text-lg font-medium text-slate-300">No funds found</h3>
            <p className="mt-1 text-sm">Could not retrieve funds for this category.</p>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-slate-800 bg-slate-900/30 backdrop-blur-sm">
          <CardHeader className="border-b border-slate-800/80 pb-4">
            <CardTitle className="text-lg font-medium text-slate-100">{activeCategory} Comparison</CardTitle>
            <CardDescription className="text-slate-400">
              {sortedFunds.length} schemes{data.source ? ` · Source: ${data.source}` : ""}. A dash indicates a metric the feed did not provide.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader className="bg-slate-950/60">
                  <TableRow className="border-slate-800/80 hover:bg-transparent">
                    <TableHead className="w-[180px] text-slate-300 font-semibold">AMC</TableHead>
                    <TableHead className="min-w-[220px] text-slate-300 font-semibold">Fund Name</TableHead>
                    <TableHead className="min-w-[115px] text-right text-slate-300 font-semibold">Latest NAV</TableHead>
                    <TableHead
                      className="text-right text-slate-300 font-semibold cursor-pointer hover:text-sky-400 transition-colors"
                      onClick={() => handleSort("1Y")}
                    >
                      1Y CAGR{renderSortIndicator("1Y")}
                    </TableHead>
                    <TableHead
                      className="text-right text-slate-300 font-semibold cursor-pointer hover:text-sky-400 transition-colors"
                      onClick={() => handleSort("3Y")}
                    >
                      3Y CAGR{renderSortIndicator("3Y")}
                    </TableHead>
                    <TableHead
                      className="text-right text-slate-300 font-semibold cursor-pointer hover:text-sky-400 transition-colors"
                      onClick={() => handleSort("5Y")}
                    >
                      5Y CAGR{renderSortIndicator("5Y")}
                    </TableHead>
                    <TableHead className="text-right text-slate-300 font-semibold">Volatility</TableHead>
                    <TableHead
                      className="text-right text-slate-300 font-semibold cursor-pointer hover:text-sky-400 transition-colors"
                      onClick={() => handleSort("sharpe")}
                    >
                      Sharpe{renderSortIndicator("sharpe")}
                    </TableHead>
                    <TableHead className="text-right text-slate-300 font-semibold">Sortino</TableHead>
                    <TableHead className="text-right text-slate-300 font-semibold">P/E</TableHead>
                    <TableHead className="text-right text-slate-300 font-semibold">TER</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedFunds.map((fund, idx) => (
                    <TableRow key={fund.schemeCode || idx} className="border-slate-800/60 hover:bg-slate-800/20">
                      <TableCell className="font-semibold text-slate-300">{fund.amc || "—"}</TableCell>
                      <TableCell className="text-slate-200">
                        {fund.schemeName}
                        {(fund.plan || fund.option) && <span className="block text-xs text-slate-400">{[fund.plan, fund.option].filter(Boolean).join(" · ")}</span>}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fund.nav != null && Number.isFinite(Number(fund.nav)) ? inr.format(Number(fund.nav)) : "—"}
                        {fund.navDate && <span className="block whitespace-nowrap text-xs text-slate-400">{fund.navDate}</span>}
                      </TableCell>
                      {renderCagrCell(fund.cagr?.["1Y"])}
                      {renderCagrCell(fund.cagr?.["3Y"])}
                      {renderCagrCell(fund.cagr?.["5Y"])}
                      <TableCell className="text-right font-mono text-slate-300">{formatNumber(fund.risk?.volatility)}</TableCell>
                      <TableCell className="text-right font-mono text-violet-400">{formatNumber(fund.risk?.sharpe)}</TableCell>
                      <TableCell className="text-right font-mono text-violet-400">{formatNumber(fund.risk?.sortino)}</TableCell>
                      <TableCell className="text-right font-mono text-amber-500">{formatNumber(fund.valuation?.pe)}</TableCell>
                      <TableCell className="text-right font-mono text-rose-400">{formatPercent(fund.expenseRatio)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function FundsTableSkeleton() {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/20 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <Skeleton className="h-6 w-48 bg-slate-800" />
        <Skeleton className="h-4 w-32 bg-slate-800" />
      </div>
      <div className="space-y-3">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-12 w-full bg-slate-800/60" />
        ))}
      </div>
    </div>
  );
}
