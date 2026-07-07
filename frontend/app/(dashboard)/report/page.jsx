"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend
} from "recharts";

const COLORS = [
  "#38bdf8", // sky-400
  "#34d399", // emerald-400
  "#fbbf24", // amber-400
  "#a78bfa", // violet-400
  "#f43f5e", // rose-400
  "#22d3ee", // cyan-400
  "#fb923c", // orange-400
  "#6366f1", // indigo-400
];

function ReportContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const reportId = searchParams.get("id");

  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [report, setReport] = useState(null);
  const [includeNews, setIncludeNews] = useState(true);
  const [isClient, setIsClient] = useState(false);

  // Error handling states
  const [serviceDown, setServiceDown] = useState(false);
  const [rateLimited, setRateLimited] = useState(false);
  const [interrupted, setInterrupted] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  // Fetch existing report if ID is present
  useEffect(() => {
    if (reportId) {
      const fetchReport = async () => {
        setLoading(true);
        setError(null);
        try {
          const res = await fetch(`/api/reports/${reportId}`);
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || "Failed to fetch report");
          }
          const data = await res.json();
          setReport(data);
          setMarkdown(data.markdown || "");
        } catch (err) {
          setError(err.message);
        } finally {
          setLoading(false);
        }
      };
      fetchReport();
    } else {
      setReport(null);
      setMarkdown("");
      setError(null);
    }
  }, [reportId]);

  const handleGenerateReport = async () => {
    setGenerating(true);
    setLoading(true);
    setMarkdown("");
    setReport(null);
    setStatusMessage("Initializing report generation...");
    setError(null);
    setServiceDown(false);
    setRateLimited(false);
    setInterrupted(false);
    setOffline(false);

    try {
      const response = await fetch("/api/reports/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ includeNews }),
      });

      if (response.status === 429) {
        setRateLimited(true);
        throw new Error("Too many requests. Please wait.");
      }
      if (response.status === 503) {
        setServiceDown(true);
        throw new Error("AI service temporarily unavailable. Using rule-based analysis.");
      }
      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.error || "Report generation failed");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let completeReceived = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          if (!completeReceived) {
            setInterrupted(true);
          }
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        let boundary = buffer.indexOf("\n\n");
        while (boundary !== -1) {
          const rawMessage = buffer.slice(0, boundary + 2);
          buffer = buffer.slice(boundary + 2);

          const lines = rawMessage.split("\n");
          let eventName = "";
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventName = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              dataStr = line.slice(6).trim();
            }
          }

          if (eventName === "status" && dataStr) {
            try {
              const statusData = JSON.parse(dataStr);
              setStatusMessage(statusData.message || "Generating...");
            } catch (_) {}
          } else if (eventName === "markdown_chunk" && dataStr) {
            try {
              const chunkData = JSON.parse(dataStr);
              if (chunkData.chunk) {
                setMarkdown((prev) => prev + chunkData.chunk);
              }
            } catch (_) {}
          } else if (eventName === "complete" && dataStr) {
            completeReceived = true;
            try {
              const completeData = JSON.parse(dataStr);
              if (completeData.report_json) {
                setReport(completeData.report_json);
                setMarkdown(completeData.report_json.markdown || "");
              }
            } catch (_) {}
          } else if (eventName === "error" && dataStr) {
            try {
              const errData = JSON.parse(dataStr);
              throw new Error(errData.error || "Generation error");
            } catch (e) {
              setError(e.message);
            }
          }

          boundary = buffer.indexOf("\n\n");
        }
      }
    } catch (err) {
      if (err.name === "TypeError" || err.message.includes("fetch failed")) {
        setOffline(true);
        setStatusMessage("Offline. Retrying automatically in 3 seconds...");
        setTimeout(() => {
          handleGenerateReport();
        }, 3000);
        return;
      }
      setError(err.message);
    } finally {
      setGenerating(false);
      setLoading(false);
    }
  };

  const handleDownloadMarkdown = () => {
    if (!markdown) return;
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `portfolio-report-${reportId || "new"}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const chartData = report?.portfolioSummary?.sectorAllocation
    ? Object.entries(report.portfolioSummary.sectorAllocation).map(([name, value]) => ({
        name,
        value: Math.round(value * 1000) / 10,
      }))
    : [];

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

  if (loading && !generating) {
    return <ReportLoadingState message={statusMessage || "Loading report..."} />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Advisory Report</h1>
          <p className="text-sm text-slate-400">
            {reportId
              ? `Viewing saved report: ${reportId}`
              : "Generate a comprehensive analysis of your confirmed holdings."}
          </p>
        </div>
        {report && (
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleDownloadMarkdown}>
              Download Report (.md)
            </Button>
            {reportId && (
              <Button variant="outline" size="sm" onClick={() => router.push("/report")}>
                Generate New
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Banners for Errors */}
      {serviceDown && (
        <div className="rounded-lg border border-amber-900 bg-amber-950/20 p-3 text-sm text-amber-400">
          ⚠️ AI service temporarily unavailable. Using rule-based analysis.
        </div>
      )}
      {rateLimited && (
        <div className="rounded-lg border border-red-900 bg-red-950/20 p-3 text-sm text-red-400">
          ⚠️ Too many requests. Please wait.
        </div>
      )}
      {offline && (
        <div className="rounded-lg border border-sky-950 bg-sky-950/20 p-3 text-sm text-sky-400 animate-pulse">
          ⚠️ Connection offline. Retrying automatically in 3 seconds...
        </div>
      )}
      {interrupted && !report && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/10 p-4 text-center space-y-2">
          <p className="text-sm text-slate-300">⚠️ Report stream was interrupted before completion.</p>
          <Button size="sm" variant="outline" className="border-slate-700" onClick={handleGenerateReport}>
            Retry Report Generation
          </Button>
        </div>
      )}

      {/* Main View Area */}
      {error && (
        <div className="rounded-xl border border-red-950 bg-red-950/20 p-4 text-sm text-red-400">
          <p className="font-medium">Error: {error}</p>
          <Button variant="outline" size="sm" className="mt-3 border-red-900/50 hover:bg-red-950/50" onClick={handleGenerateReport}>
            Retry Generation
          </Button>
        </div>
      )}

      {!report && !generating && !error && (
        <Card className="border-slate-800 bg-slate-900/40">
          <CardHeader>
            <CardTitle>Portfolio Risk & Advisory Analysis</CardTitle>
            <CardDescription>
              Our system retrieves relevant SEBI diversification guidelines, latest news sentiments, and computes concentrations.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center space-x-3 rounded-lg border border-slate-800 bg-slate-900/60 p-4">
              <input
                type="checkbox"
                id="includeNews"
                className="h-4 w-4 rounded border-slate-700 bg-slate-800 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-900"
                checked={includeNews}
                onChange={(e) => setIncludeNews(e.target.checked)}
              />
              <label htmlFor="includeNews" className="text-sm font-medium text-slate-200 cursor-pointer">
                Include live news & market sentiment analysis (slows generation slightly)
              </label>
            </div>
            <Button size="lg" className="w-full bg-sky-600 hover:bg-sky-500 text-slate-50" onClick={handleGenerateReport}>
              Generate Report
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Streaming / Generation Progress */}
      {generating && !report && (
        <Card className="border-slate-800 bg-slate-900/40">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium text-sky-400">Streaming Report Generation</CardTitle>
              <span className="text-xs text-slate-500 animate-pulse">Running Agent Graph...</span>
            </div>
            <CardDescription className="text-slate-200 mt-2 font-mono text-xs">
              Status: {statusMessage}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={markdown ? 80 : 30} className="h-1.5" />
            <p className="text-xs text-slate-400">
              The graph is currently fetching live circulars and running RAG recommendations.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Report Layout */}
      {(markdown || report) && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-10">
          {/* Markdown Content */}
          <div className="lg:col-span-7 space-y-4">
            <Card className="border-slate-800 bg-slate-900/30">
              <CardContent className="p-6 md:p-8 prose prose-invert max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h1: ({node, ...props}) => <h1 className="text-xl font-bold border-b border-slate-800 pb-2 mt-6 mb-4 text-slate-50" {...props} />,
                    h2: ({node, ...props}) => <h2 className="text-lg font-semibold mt-6 mb-3 text-slate-100" {...props} />,
                    h3: ({node, ...props}) => <h3 className="text-md font-semibold mt-4 mb-2 text-slate-200" {...props} />,
                    p: ({node, ...props}) => <p className="text-sm leading-relaxed text-slate-300 mb-4" {...props} />,
                    ul: ({node, ...props}) => <ul className="list-disc pl-5 mb-4 text-sm text-slate-300 space-y-1" {...props} />,
                    ol: ({node, ...props}) => <ol className="list-decimal pl-5 mb-4 text-sm text-slate-300 space-y-1" {...props} />,
                    li: ({node, ...props}) => <li className="text-slate-300" {...props} />,
                    blockquote: ({node, ...props}) => <blockquote className="border-l-4 border-slate-700 pl-4 italic text-slate-400 my-4" {...props} />,
                    table: ({node, ...props}) => (
                      <div className="overflow-x-auto my-4">
                        <table className="w-full text-left text-sm border-collapse border border-slate-800" {...props} />
                      </div>
                    ),
                    thead: ({node, ...props}) => <thead className="bg-slate-900/60 text-slate-200 border-b border-slate-800" {...props} />,
                    tbody: ({node, ...props}) => <tbody className="divide-y divide-slate-800" {...props} />,
                    tr: ({node, ...props}) => <tr className="hover:bg-slate-900/30 transition-colors" {...props} />,
                    th: ({node, ...props}) => <th className="p-3 font-medium border border-slate-800" {...props} />,
                    td: ({node, ...props}) => <td className="p-3 border border-slate-800 text-slate-300" {...props} />,
                  }}
                >
                  {markdown}
                </ReactMarkdown>
              </CardContent>
            </Card>
          </div>

          {/* Sidebar Metadata & Charts */}
          <div className="lg:col-span-3 space-y-6">
            {report && (
              <>
                {/* Summary Card */}
                <Card className="border-slate-800 bg-slate-900/40">
                  <CardHeader>
                    <CardTitle className="text-sm font-semibold">Risk Summary</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-400">Risk Level</span>
                      <span className={`rounded px-2.5 py-0.5 text-xs font-semibold border ${getRiskBadgeColor(report.portfolioSummary?.overallRiskLevel)}`}>
                        {report.portfolioSummary?.overallRiskLevel || "LOW"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-400">Total Value</span>
                      <span className="text-sm font-semibold text-slate-100">
                        ₹{(report.portfolioSummary?.totalValue || 0).toLocaleString("en-IN")}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-400">Holdings Count</span>
                      <span className="text-sm font-semibold text-slate-100">
                        {report.portfolioSummary?.holdingsCount || 0}
                      </span>
                    </div>
                  </CardContent>
                </Card>

                {/* Sector Allocation Pie Chart */}
                {chartData.length > 0 && (
                  <Card className="border-slate-800 bg-slate-900/40">
                    <CardHeader>
                      <CardTitle className="text-sm font-semibold">Sector Allocation (%)</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-[240px] w-full flex items-center justify-center">
                        {isClient && (
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie
                                data={chartData}
                                cx="50%"
                                cy="50%"
                                labelLine={false}
                                outerRadius={65}
                                fill="#8884d8"
                                dataKey="value"
                              >
                                {chartData.map((entry, index) => (
                                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                ))}
                              </Pie>
                              <Tooltip formatter={(value) => `${value}%`} />
                            </PieChart>
                          </ResponsiveContainer>
                        )}
                      </div>
                      {/* Simple legend list since Recharts Legend can be verbose */}
                      <div className="mt-2 space-y-1.5">
                        {chartData.map((item, index) => (
                          <div key={item.name} className="flex items-center justify-between text-xs">
                            <div className="flex items-center space-x-1.5">
                              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                              <span className="text-slate-300 truncate max-w-[120px]">{item.name}</span>
                            </div>
                            <span className="font-mono text-slate-400">{item.value}%</span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Recommendations */}
                {report.recommendations?.length > 0 && (
                  <Card className="border-slate-800 bg-slate-900/40">
                    <CardHeader>
                      <CardTitle className="text-sm font-semibold">Top Actions</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {report.recommendations.map((rec, i) => (
                        <div key={i} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-slate-200">{rec.ticker}</span>
                            <span className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded ${
                              rec.action === "TRIM" ? "bg-red-950 text-red-400 border border-red-900/30" : "bg-sky-950 text-sky-400 border border-sky-900/30"
                            }`}>
                              {rec.action}
                            </span>
                          </div>
                          <p className="text-[11px] leading-relaxed text-slate-400">{rec.reasoning}</p>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ReportLoadingState({ message }) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Advisory Report</h1>
        <p className="text-sm text-slate-400">{message}</p>
      </div>
      <Card className="border-slate-800 bg-slate-900/40">
        <CardContent className="p-12 text-center space-y-4">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
          <p className="text-sm text-slate-400 animate-pulse">{message}</p>
        </CardContent>
      </Card>
    </div>
  );
}

// Fallback skeleton
function ReportLoading() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="h-8 w-48 rounded bg-slate-800 animate-pulse" />
        <div className="h-4 w-96 rounded bg-slate-800 animate-pulse" />
      </div>
      <Card className="border-slate-800 bg-slate-900/40">
        <CardContent className="h-64 animate-pulse bg-slate-800/10 rounded-xl" />
      </Card>
    </div>
  );
}

export default function ReportPage() {
  return (
    <Suspense fallback={<ReportLoading />}>
      <ReportContent />
    </Suspense>
  );
}
