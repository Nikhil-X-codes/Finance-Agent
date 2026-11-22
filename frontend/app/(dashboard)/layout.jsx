import Link from "next/link";
import { redirect } from "next/navigation";
import DashboardNav from "@/components/dashboard-nav";
import { getSession } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function DashboardLayout({ children }) {
  const session = await getSession();
  if (!session.userId) redirect("/login");

  return (
    <div className="dashboard-shell">
      <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-slate-950 focus:p-3">
        Skip to content
      </a>
      <header className="dashboard-header">
        <Link href="/" className="dashboard-brand">
          <span className="dashboard-mark" aria-hidden="true" />
          Finance Agent
        </Link>
        <div className="dashboard-account">
          <span className="hidden min-w-0 truncate text-sm text-slate-400 sm:block">{session.email}</span>
          <form action="/api/auth/logout" method="POST" className="shrink-0">
            <button type="submit" className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800">
              Sign out
            </button>
          </form>
        </div>
      </header>
      <DashboardNav />
      <div className="dashboard-body">
        <main id="content" tabIndex={-1} className="mx-auto w-full max-w-7xl flex-1 px-5 py-8 sm:px-8 sm:py-10 xl:px-12">
          {children}
        </main>
        <footer className="border-t border-slate-800 px-5 py-4 text-xs leading-relaxed text-slate-400 sm:px-8 xl:px-12">
          <p className="mx-auto max-w-7xl">For information only. Consult a SEBI-registered adviser before investing.</p>
        </footer>
      </div>
    </div>
  );
}
