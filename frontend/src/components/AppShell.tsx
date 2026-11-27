import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, Link } from "react-router-dom";
import { request } from "../lib/api";
import { useMe } from "../lib/auth";
import { BrandName } from "./Brand";

const NAV = [
  { to: "/today", label: "Today" },
  { to: "/learn", label: "Learn" },
  { to: "/plan", label: "Plan" },
  { to: "/progress", label: "Progress" },
  { to: "/me", label: "Me" },
];

function useUnread() {
  return useQuery({
    queryKey: ["notifications", "count"],
    queryFn: () => request<{ count: number }>("/notifications/unread-count"),
    refetchInterval: 60_000,
    select: (data) => data.count,
  });
}

function Alerts({ className = "" }: { className?: string }) {
  const unread = useUnread();
  const count = unread.data ?? 0;
  return (
    <Link to="/notifications" className={`inline-flex min-h-11 items-center gap-2 font-display text-lg font-semibold uppercase tracking-wide ${className}`}>
      Alerts
      {count > 0 && (
        <span className="num min-w-6 bg-flag px-1.5 text-center text-base text-paper" aria-label={`${count} unread`}>
          {count}
        </span>
      )}
    </Link>
  );
}

export function AppShell() {
  const me = useMe();
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-whistle focus:p-3">
        Skip to content
      </a>
      <aside className="hidden border-r-2 border-ink bg-paper-2 lg:flex lg:flex-col lg:justify-between lg:px-5 lg:py-6">
        <div className="space-y-8">
          <BrandName />
          <nav aria-label="Main" className="flex flex-col gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex min-h-11 items-center border-l-4 px-3 font-display text-2xl font-semibold uppercase tracking-wide ${
                    isActive ? "border-whistle bg-paper text-ink" : "border-transparent text-ink-soft hover:bg-paper"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="space-y-1">
          <Alerts />
          <p className="truncate text-sm text-ink-soft">{me.data?.name}</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="flex items-center justify-between border-b-2 border-ink bg-paper px-4 lg:hidden">
          <BrandName className="!text-2xl" />
          <Alerts />
        </header>
        <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-4 pb-28 pt-6 lg:px-8 lg:pb-12 lg:pt-8">
          <Outlet />
        </main>
        <nav
          aria-label="Main"
          className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t-2 border-ink bg-paper pb-[env(safe-area-inset-bottom)] lg:hidden"
        >
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex min-h-14 items-center justify-center border-t-4 font-display text-lg font-semibold uppercase tracking-wide ${
                  isActive ? "border-whistle bg-paper-2 text-ink" : "border-transparent text-ink-soft"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
