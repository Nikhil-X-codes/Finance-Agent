"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";

export default function ReportHistoryPage() {
  const router = useRouter();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Edit state
  const [editingId, setEditingId] = useState(null);
  const [editingName, setEditingName] = useState("");
  const [savingId, setSavingId] = useState(null);

  // Delete state
  const [deletingId, setDeletingId] = useState(null);

  const fetchReports = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/reports");
      if (!res.ok) throw new Error("Failed to load reports history");
      const data = await res.json();
      setReports(data.reports || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  const startRename = (e, report) => {
    e.stopPropagation();
    setEditingId(report.id);
    setEditingName(report.name);
  };

  const cancelRename = (e) => {
    if (e) e.stopPropagation();
    setEditingId(null);
    setEditingName("");
  };

  const handleRename = async (e, reportId) => {
    e.stopPropagation();
    if (!editingName.trim()) return;

    setSavingId(reportId);
    try {
      const res = await fetch(`/api/reports/${reportId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editingName.trim() }),
      });

      if (!res.ok) throw new Error("Rename failed");

      setReports((prev) =>
        prev.map((r) => (r.id === reportId ? { ...r, name: editingName.trim() } : r))
      );
      setEditingId(null);
      setEditingName("");
    } catch (err) {
      alert(err.message);
    } finally {
      setSavingId(null);
    }
  };

  const handleDelete = async (e, reportId) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this report?")) return;

    setDeletingId(reportId);
    try {
      const res = await fetch(`/api/reports/${reportId}`, {
        method: "DELETE",
      });

      if (!res.ok) throw new Error("Delete failed");

      setReports((prev) => prev.filter((r) => r.id !== reportId));
    } catch (err) {
      alert(err.message);
    } finally {
      setDeletingId(null);
    }
  };

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
    return <HistorySkeleton />;
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-900/50 bg-red-950/20 p-6 text-center text-red-400">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-50">Report History</h1>
          <p className="text-sm text-slate-400">
            View, rename, and delete previously generated advisory reports.
          </p>
        </div>
        <Button className="bg-sky-600 hover:bg-sky-500 text-slate-50" onClick={() => router.push("/report")}>
          Generate New Report
        </Button>
      </div>

      {reports.length === 0 ? (
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
          }
          title="No reports generated yet"
          description="Generate your first advisory report to receive detailed risk flags and recommendations."
          actionLabel="Generate Report"
          actionHref="/report"
        />
      ) : (
        <Card className="border-slate-800 bg-slate-900/30">
          <CardHeader className="px-6 py-4">
            <CardTitle className="text-sm font-semibold text-slate-200">Advisory Log</CardTitle>
            <CardDescription>Click on any row to view the full details and recommendations.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader className="bg-slate-900/50 border-b border-slate-800">
                <TableRow className="border-slate-800">
                  <TableHead className="px-6 py-3 font-medium text-slate-400">Report Name</TableHead>
                  <TableHead className="px-6 py-3 font-medium text-slate-400">Created Date</TableHead>
                  <TableHead className="px-6 py-3 font-medium text-slate-400">Overall Risk Level</TableHead>
                  <TableHead className="px-6 py-3 font-medium text-slate-400 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reports.map((report) => (
                  <TableRow
                    key={report.id}
                    className="border-b border-slate-800/60 hover:bg-slate-900/40 cursor-pointer transition-colors"
                    onClick={() => router.push(`/report?id=${report.id}`)}
                  >
                    <TableCell className="px-6 py-4">
                      {editingId === report.id ? (
                        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                          <Input
                            value={editingName}
                            onChange={(e) => setEditingName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleRename(e, report.id);
                              if (e.key === "Escape") cancelRename(e);
                            }}
                            className="h-8 w-64 bg-slate-950 text-slate-200 text-sm border-slate-800"
                            autoFocus
                            disabled={savingId === report.id}
                          />
                          <button
                            onClick={(e) => handleRename(e, report.id)}
                            disabled={savingId === report.id}
                            className="text-xs text-sky-400 hover:text-sky-300 font-semibold px-1 py-0.5"
                          >
                            Save
                          </button>
                          <button
                            onClick={cancelRename}
                            disabled={savingId === report.id}
                            className="text-xs text-slate-500 hover:text-slate-400 font-semibold px-1 py-0.5"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 group">
                          <span className="text-sm font-medium text-slate-200">{report.name}</span>
                          <button
                            onClick={(e) => startRename(e, report)}
                            className="text-xs text-slate-500 hover:text-sky-400 opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Rename Report"
                          >
                            ✏️
                          </button>
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="px-6 py-4 text-sm text-slate-350">
                      {new Date(report.createdAt).toLocaleString()}
                    </TableCell>
                    <TableCell className="px-6 py-4">
                      <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${getRiskBadgeColor(report.overallRiskLevel)}`}>
                        {report.overallRiskLevel}
                      </span>
                    </TableCell>
                    <TableCell className="px-6 py-4 text-right">
                      <div className="flex justify-end items-center gap-2" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={(e) => handleDelete(e, report.id)}
                          disabled={deletingId === report.id}
                          className="rounded p-1.5 text-slate-500 hover:bg-red-950/50 hover:text-red-400 transition-colors disabled:opacity-50"
                          title="Delete report"
                        >
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="3 6 5 6 21 6" />
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                          </svg>
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-48 bg-slate-800" />
        <Skeleton className="h-4 w-72 bg-slate-800" />
      </div>
      <Card className="border-slate-800 bg-slate-900/30 p-4 space-y-3">
        <Skeleton className="h-10 w-full bg-slate-800" />
        <Skeleton className="h-12 w-full bg-slate-800/60" />
        <Skeleton className="h-12 w-full bg-slate-800/60" />
        <Skeleton className="h-12 w-full bg-slate-800/60" />
      </Card>
    </div>
  );
}
