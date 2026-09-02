"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  label: string;
  href: string;
  icon: string;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const sections: NavSection[] = [
  {
    title: "Overview",
    items: [{ label: "Dashboard", href: "/", icon: "◎" }],
  },
  {
    title: "Detection",
    items: [
      { label: "Detected Rings", href: "/rings", icon: "⬡" },
      { label: "Transactions", href: "/transactions", icon: "⇉" },
    ],
  },
  {
    title: "Analysis",
    items: [
      { label: "Graph Analysis", href: "/graph", icon: "◇" },
      { label: "Fairness Audit", href: "/fairness", icon: "⊞" },
      { label: "Metrics", href: "/metrics", icon: "⊿" },
    ],
  },
];

export default function Sidebar({ connectionState }: { connectionState: string }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  const connectionDot =
    connectionState === "open"
      ? "bg-success"
      : connectionState === "reconnecting"
        ? "bg-warning"
        : connectionState === "connecting"
          ? "bg-warning"
          : "bg-danger";

  return (
    <>
      {/* Mobile hamburger */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="fixed left-3 top-3 z-50 flex h-8 w-8 items-center justify-center rounded-md border border-border bg-surface text-fg-secondary md:hidden"
        aria-label="Toggle navigation"
      >
        {mobileOpen ? "✕" : "☰"}
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-border bg-surface transition-transform duration-200 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        } md:translate-x-0 ${collapsed ? "md:w-16" : "md:w-60"}`}
      >
        {/* Logo area */}
        <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-xs font-bold text-white">
            FS
          </span>
          {!collapsed && (
            <div className="flex flex-col overflow-hidden">
              <span className="text-sm font-semibold tracking-tight text-fg">
                Fraud Sentinel
              </span>
              <span className="flex items-center gap-1.5 text-[10px] text-fg-muted">
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${connectionDot}`} />
                {connectionState === "open" ? "Stream active" : connectionState}
              </span>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {sections.map((section) => (
            <div key={section.title} className="mb-3">
              {!collapsed && (
                <div className="mb-1 px-2 text-[10px] font-medium uppercase tracking-wider text-fg-muted">
                  {section.title}
                </div>
              )}
              <div className="flex flex-col gap-0.5">
                {section.items.map((item) => {
                  const active = isActive(item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                      className={`flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors ${
                        active
                          ? "bg-surface-subtle text-fg"
                          : "text-fg-secondary hover:bg-surface-hover hover:text-fg"
                      }`}
                    >
                      <span
                        className={`flex h-5 w-5 shrink-0 items-center justify-center text-xs ${
                          active ? "text-accent" : "text-fg-muted"
                        }`}
                      >
                        {item.icon}
                      </span>
                      {!collapsed && <span>{item.label}</span>}
                      {active && !collapsed && (
                        <span className="ml-auto h-1.5 w-1.5 rounded-full bg-accent" />
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* Collapse toggle (desktop only) */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="hidden border-t border-border px-2 py-2.5 text-center text-xs text-fg-muted transition-colors hover:bg-surface-hover hover:text-fg-secondary md:block"
        >
          {collapsed ? "→" : "←"}
        </button>
      </aside>
    </>
  );
}
