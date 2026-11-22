"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const sections = [
  ["/", "Portfolio"], ["/trade-log", "Trades"], ["/stocks", "Stocks"], ["/funds", "Funds"],
  ["/report", "Reports"], ["/report/history", "Report history"], ["/qa", "Q&A"],
];

export default function DashboardNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Main navigation" className="dashboard-nav">
      {sections.map(([href, label]) => {
        const active = pathname === href ||
          (href === "/" && pathname.startsWith("/portfolio")) ||
          (href === "/stocks" && pathname.startsWith("/stocks/"));
        return (
          <Link key={href} href={href} aria-current={active ? "page" : undefined}>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
