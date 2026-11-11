import { NavLink, Outlet } from "react-router-dom";
import { useMeta } from "../api/hooks";
import { formatLongDate } from "../lib/format";
import { PhaseBadge } from "./ui";

export interface NavItem {
  path: string;
  label: string;
  icon: string; // SVG path data, 20x20 viewBox
  /** Milestone or phase in which the page is delivered; omitted when available now. */
  availableIn?: string;
}

export const NAV: NavItem[] = [
  { path: "/", label: "Overview", icon: "M3 3h6v6H3zM11 3h6v6h-6zM3 11h6v6H3zM11 11h6v6h-6z" },
  { path: "/analyst", label: "AI Analyst", icon: "M4 4h12v9H8l-4 3z" },
  { path: "/production", label: "Production", icon: "M3 17V9l4 3V9l4 3V5h6v12z", availableIn: "Phase 2" },
  { path: "/downtime", label: "Downtime", icon: "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14zm0 3v4l3 2", availableIn: "Phase 2" },
  { path: "/quality", label: "Quality", icon: "M10 2l6 3v5c0 4-3 7-6 8-3-1-6-4-6-8V5z", availableIn: "Phase 2" },
  { path: "/knowledge", label: "Knowledge Base", icon: "M4 3h9l3 3v11H4zM7 8h6M7 11h6M7 14h4", availableIn: "Phase 3" },
  { path: "/activity", label: "Agent Activity", icon: "M2 10h4l2-5 4 10 2-5h4", availableIn: "Phase 2" },
  { path: "/evaluations", label: "Evaluations", icon: "M4 10l4 4 8-9", availableIn: "Phase 4" },
  { path: "/settings", label: "Settings", icon: "M10 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM10 2v2M10 16v2M2 10h2M16 10h2M4.2 4.2l1.4 1.4M14.4 14.4l1.4 1.4M4.2 15.8l1.4-1.4M14.4 5.6l1.4-1.4" },
];

export function Layout() {
  const meta = useMeta();
  return (
    <div className="flex min-h-screen bg-page">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col bg-navy-950 text-navy-300 md:flex">
        <div className="flex items-center gap-2 px-5 py-5">
          <span aria-hidden className="flex h-7 w-7 items-center justify-center rounded-md bg-series-1 text-sm font-bold text-white">O</span>
          <span className="text-sm font-semibold tracking-wide text-white">OpsPilot AI</span>
        </div>
        <nav aria-label="Main" className="flex-1 space-y-0.5 px-3">
          {NAV.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm ${
                  isActive ? "bg-navy-800 font-medium text-white" : "hover:bg-navy-900 hover:text-white"
                }`
              }
            >
              <svg aria-hidden viewBox="0 0 20 20" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round">
                <path d={item.icon} />
              </svg>
              <span className="flex-1">{item.label}</span>
              {item.availableIn && <PhaseBadge phase={item.availableIn} />}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-navy-800 px-5 py-4 text-[11px] leading-5 text-navy-400">
          <p>Synthetic data · local only</p>
          {meta.data && (
            <p>
              {meta.data.clockPinned ? "Demo clock" : "Clock"}: {formatLongDate(meta.data.today)} ({meta.data.plantTimeZone})
            </p>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Compact navigation for narrow screens */}
        <nav aria-label="Main (compact)" className="flex gap-1 overflow-x-auto bg-navy-950 px-3 py-2 md:hidden">
          {NAV.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) => `whitespace-nowrap rounded px-2.5 py-1 text-xs ${isActive ? "bg-navy-800 text-white" : "text-navy-300"}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function PageHeader({ title, description, children }: { title: string; description?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h1 className="text-xl font-semibold text-ink">{title}</h1>
        {description && <p className="mt-1 text-sm text-ink-secondary">{description}</p>}
      </div>
      {children}
    </div>
  );
}
