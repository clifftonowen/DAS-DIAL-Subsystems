// Sidebar.jsx — Left navigation panel for the dashboard shell.
// Rendered once inside Dashboard.jsx; stays visible across all pages.
//
// Uses react-router-dom <NavLink> which automatically receives
// { isActive } so we can toggle the red active style without
// any manual state tracking.

import { NavLink } from "react-router-dom";

// Nav items — icon, label, and the route path they link to.
// Matches the prototype sidebar: 🏠 Main | 👥 Learners | ⚡ Generate
const NAV_ITEMS = [
  { icon: "🏠", label: "Main",      to: "/" },
  { icon: "👥", label: "Learners",  to: "/learners" },
  { icon: "⚡", label: "Generate",  to: "/generate" },
];

export default function Sidebar() {
  return (
    // The <nav> sits in the left column of .shell-grid (defined in index.css)
    <nav className="flex flex-col gap-1 overflow-y-auto border-r border-brand-border bg-white px-3 py-5">

      {/* ── Primary nav links ── */}
      {NAV_ITEMS.map(({ icon, label, to }) => (
        <NavLink
          key={to}
          to={to}
          // end prop on "/" prevents it matching every sub-route
          end={to === "/"}
          className={({ isActive }) =>
            [
              // Base styles — match prototype .nav-item
              "flex items-center gap-2.5 rounded-lg px-3.5 py-2.5",
              "text-sm font-medium transition-all duration-150",
              // Active: brand red background + white text (prototype .nav-item.active)
              // Inactive: muted text, hover grey background
              isActive
                ? "bg-brand-primary text-brand-on-primary"
                : "text-brand-fg-muted hover:bg-brand-muted hover:text-brand-fg",
            ].join(" ")
          }
        >
          {/* Icon opacity 0.7 when inactive, full when active — matches prototype */}
          {({ isActive }) => (
            <>
              <span className={`text-lg w-5 text-center ${isActive ? "opacity-100" : "opacity-70"}`}>
                {icon}
              </span>
              {label}
            </>
          )}
        </NavLink>
      ))}

      {/* ── Spacer pushes settings button to the bottom ── */}
      <div className="flex-1" />

      {/* ── Settings button (static, no route yet) ── */}
      <div className="border-t border-brand-border pt-3">
        <button
          className="flex w-full items-center gap-2.5 rounded-lg px-3.5 py-2.5
                     text-xs font-medium text-brand-fg-muted
                     transition-all duration-150 hover:bg-brand-muted hover:text-brand-fg"
        >
          <span className="w-5 text-center text-lg opacity-70">⚙️</span>
          Settings
        </button>
      </div>
    </nav>
  );
}
