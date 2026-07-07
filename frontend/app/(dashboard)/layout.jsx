import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";

export default async function DashboardLayout({ children }) {
  const session = await getSession();

  if (!session.userId) {
    redirect("/login");
  }

  return (
    <div className="min-h-screen bg-slate-950">
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-8">
            <a href="/" className="text-lg font-semibold tracking-tight text-slate-50">
              Portfolio Advisor
            </a>
            <nav className="hidden items-center gap-1 sm:flex">
              <a
                href="/"
                className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-50"
              >
                Dashboard
              </a>

              <a
                href="/trade-log"
                className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-50"
              >
                Trade Log
              </a>
              <a
                href="/funds"
                className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-50"
              >
                Funds
              </a>
              <a
                href="/stocks"
                className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-50"
              >
                Stocks
              </a>
              <a
                href="/report"
                className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-50"
              >
                Advisory Report
              </a>
              <a
                href="/report/history"
                className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-50"
              >
                History
              </a>
              <a
                href="/qa"
                className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-50"
              >
                Q&A Assistant
              </a>

            </nav>
          </div>

          <div className="flex items-center gap-4">
            <span className="hidden text-sm text-slate-500 sm:inline">
              {session.email}
            </span>
            <form action="/api/auth/logout" method="POST">
              <button
                type="submit"
                className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-50"
              >
                Logout
              </button>
            </form>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="mx-auto max-w-6xl px-6 py-8">
        {children}
      </main>

      {/* Disclaimer footer */}
      <footer className="border-t border-slate-800 bg-slate-950 px-6 py-4">
        <p className="mx-auto max-w-6xl text-xs text-slate-600">
          This is not SEBI-registered investment advice. Consult a SEBI-registered advisor before investing.
          AI-generated recommendations are based on public data and regulatory guidelines.
          Mutual fund investments are subject to market risks.
        </p>
      </footer>
    </div>
  );
}
