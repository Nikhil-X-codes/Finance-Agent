import { cn } from "@/lib/utils";

export function Button({ className = "", variant = "default", ...props }) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-colors",
        variant === "default" ? "bg-slate-50 text-slate-950 hover:bg-slate-200" : "bg-slate-800 text-slate-50 hover:bg-slate-700",
        className
      )}
      {...props}
    />
  );
}
