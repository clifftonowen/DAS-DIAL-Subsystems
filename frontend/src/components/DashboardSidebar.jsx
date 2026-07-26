// Sidebar.jsx — Left navigation panel for the dashboard shell.
// Rendered once inside Dashboard.jsx; stays visible across all pages.
//
// Uses react-router-dom <NavLink> which automatically receives
// { isActive } so we can toggle the red active style without
// any manual state tracking.

import { NavLink } from "react-router-dom";

// Nav items — label and the route path they link to.
const NAV_ITEMS = [
  { label: "Main",      to: "/" },
  { label: "Learners",  to: "/learners" },
  { label: "Generate",  to: "/generate" },
];

export default function Sidebar() {
  return (
    // The <nav> sits in the left column of .shell-grid (defined in index.css)
    <nav className="flex flex-col gap-1 overflow-y-auto border-r border-brand-border bg-white px-3 py-5">

      {/* ── Primary nav links ── */}
      {NAV_ITEMS.map(({ label, to }) => (
        <NavLink
          key={to}
          to={to}
          // end prop on "/" prevents it matching every sub-route
          end={to === "/"}
          className={({ isActive }) =>
            [
              // Base styles — metrics per DashPreview.dc.html (12px radius, 11/14 padding)
              "flex items-center gap-2.5 rounded-xl px-3.5 py-[11px]",
              "text-sm transition-all duration-150",
              // Active: brand red background + white text, slightly heavier weight
              // Inactive: muted text, hover grey background
              isActive
                ? "bg-brand-primary font-semibold text-brand-on-primary"
                : "font-medium text-brand-fg-muted hover:bg-brand-muted hover:text-brand-fg",
            ].join(" ")
          }
        >
          {label}
        </NavLink>
      ))}

      {/* ── Spacer pushes settings button to the bottom ── */}
      <div className="flex-1" />

      {/* ── Settings button (static, no route yet) ── */}
      <div className="border-t border-brand-border pt-3">
        <button
          className="flex w-full items-center gap-2.5 rounded-xl px-3.5 py-[11px]
                     text-xs font-medium text-brand-fg-muted
                     transition-all duration-150 hover:bg-brand-muted hover:text-brand-fg"
        >
          Settings
        </button>
      </div>
    </nav>
  );
}
