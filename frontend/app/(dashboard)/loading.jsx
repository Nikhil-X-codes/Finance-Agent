import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardLoading() {
  return (
    <div className="space-y-6">
      {/* Header Skeleton */}
      <div className="space-y-2">
        <Skeleton className="h-8 w-48 bg-slate-800" />
        <Skeleton className="h-4 w-72 bg-slate-800" />
      </div>
      
      {/* KPI Cards Skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Skeleton className="h-28 bg-slate-800/60 rounded-xl" />
        <Skeleton className="h-28 bg-slate-800/60 rounded-xl" />
        <Skeleton className="h-28 bg-slate-800/60 rounded-xl" />
      </div>

      {/* Grid split skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-10 gap-6">
        <div className="lg:col-span-6 space-y-6">
          <Skeleton className="h-48 bg-slate-800/60 rounded-xl" />
          <Skeleton className="h-24 bg-slate-800/60 rounded-xl" />
        </div>
        <div className="lg:col-span-4">
          <Skeleton className="h-80 bg-slate-800/60 rounded-xl" />
        </div>
      </div>
    </div>
  );
}
