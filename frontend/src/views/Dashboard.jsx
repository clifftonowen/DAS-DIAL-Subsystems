// Dashboard.jsx — Layout shell for the authenticated dashboard.
//
// Owns the BrowserRouter so React Router (NavLink, useNavigate, useParams)
// works within the dashboard without touching main.jsx or the auth flow.
//
// Route tree:
//   /                → MainPage          (stat cards, calendar, tasks)
//   /learners        → LearnersPage      (searchable student grid)
//   /learners/:id    → LearnerDetailPage (radar chart, skill bars, alerts)
//   /generate        → GeneratePage      (autocomplete + generate activity)
//
// Shell layout (matches prototype .shell div):
//   .shell-grid (index.css: 220px sidebar | 1fr content, 100dvh)
//     ├── <header>  .shell-header  — spans both columns
//     ├── <DashboardSidebar />     — left column
//     └── <main>   <Outlet />      — right column, scrollable

import { BrowserRouter, Routes, Route, Outlet } from "react-router-dom";
import Brand from "../components/Brand";
import ProfileMenu from "../components/ProfileMenu";
import DashboardSidebar from "../components/DashboardSidebar";

// --- DASHBOARD PROTOTYPE ADDITIONS ---
// Page components — one per route
import MainPage from "./MainPage";
import LearnersPage from "./LearnersPage";
import LearnerDetailPage from "./LearnerDetailPage";
import GeneratePage from "./GeneratePage";
// --- END DASHBOARD PROTOTYPE ADDITIONS ---

// Inner shell — the actual header + sidebar + outlet layout.
// Separated from Dashboard so BrowserRouter wraps it correctly.
function DashboardShell({ session }) {
  return (
    // .shell-grid defined in index.css:
    //   grid-template-columns: 220px 1fr
    //   grid-template-rows: auto 1fr
    //   height: 100dvh
    <div className="shell-grid bg-brand-bg">

      {/* ── Header — spans both columns via .shell-header (index.css) ── */}
      <header className="shell-header flex items-center justify-between
                         border-b border-brand-border bg-white px-6 py-3
                         sticky top-0 z-10">
        <Brand />
        {/* Profile dropdown (avatar + email + Sign out) — top-right */}
        <ProfileMenu session={session} />
      </header>

      {/* ── Sidebar — left column, rendered on every page ── */}
      <DashboardSidebar />

      {/* ── Content area — React Router injects the active page here ── */}
      <main className="overflow-y-auto p-6">
        <Outlet />
      </main>

    </div>
  );
}

// Dashboard — the root component rendered by main.jsx when session exists.
// BrowserRouter lives here so it is completely self-contained within the
// dashboard and does not affect the auth flow in main.jsx.
export default function Dashboard({ session }) {
  return (
    <BrowserRouter>
      <Routes>
        {/* DashboardShell provides the header + sidebar frame for all pages */}
        <Route element={<DashboardShell session={session} />}>
          <Route index element={<MainPage />} />
          <Route path="learners" element={<LearnersPage />} />
          <Route path="learners/:id" element={<LearnerDetailPage />} />
          <Route path="generate" element={<GeneratePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
