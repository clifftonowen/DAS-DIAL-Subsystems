// MainPage.jsx — Default landing page rendered at route "/".
//
// Crisp Bright refresh (design direction 1d). Vertical stack:
//   HeroBanner    — welcome banner
//   alerts row    — StatCards, one per STAT_CARDS entry below
//   .main-layout  — Calendar (left column) + TaskList stack (right column)
//
// All three sections read live data from /dashboard/* via lib/api.

import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import HeroBanner from "../components/HeroBanner";
import StatCard from "../components/StatCard";
import Calendar from "../components/Calendar";
import TaskList from "../components/TaskList";
import { getDashboardStats, getDashboardTasks, getDashboardEvents } from "../lib/api";
import Graph from "../components/Graph";
import Modal from "../components/Modal";
import LearnerDetailPage from "./LearnerDetailPage";

// Alerts row above the calendar — one entry per card, each driven by a key on the
// /dashboard/stats response. Add a card by adding a row here; no new component needed.
const STAT_CARDS = [
  { key: "total_learners",  title: "Total Learners",
    subtitle: (n) => `${n} learners enrolled` },
  { key: "needs_profiling", title: "Missing Profiles",
    subtitle: (n) => `${n} learners missing a profile` },
  { key: "flagged",         title: "Pending Review",
    subtitle: (n) => `${n} activities awaiting review` },
];

export default function MainPage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [tasks, setTasks] = useState({ today: [], upcoming: [] });
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  // Learner row picked from the cohort graph's cluster table, shown in an overlay.
  // Owned here rather than in Graph so that component stays free of view imports.
  const [selectedLearner, setSelectedLearner] = useState(null);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const [statsData, tasksData, eventsData] = await Promise.all([
          getDashboardStats(),
          getDashboardTasks(),
          getDashboardEvents(),
        ]);

        setStats(statsData);
        
        // Transform events into simple date strings array for the calendar component
        setEvents((eventsData || []).map(e => e.event_date));

        // Group tasks by simple logic (for prototype: PENDING/DONE)
        if (tasksData) {
          const today = tasksData.filter(t => t.meta.includes('today') || t.status === 'DONE').map(t => ({
            text: t.title, meta: t.meta, done: t.status === 'DONE'
          }));
          const upcoming = tasksData.filter(t => !t.meta.includes('today') && t.status !== 'DONE').map(t => ({
            text: t.title, meta: t.meta, done: t.status === 'DONE'
          }));
          setTasks({ today, upcoming });
        }
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        setLoading(false);
      }
    }
    loadDashboard();
  }, []);

  const todayLabel = new Date().toLocaleDateString("en-SG", { day: "numeric", month: "long" });

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-brand-border border-t-brand-primary"></div>
      </div>
    );
  }

  return (
    // No h-full: this column is taller than the viewport, and h-full would let
    // flex-shrink compress every child to fit (clipping the hero, which is
    // overflow-hidden). The <main> in Dashboard.jsx already scrolls.
    <div className="flex flex-col gap-[18px]">
      {/* ── Welcome banner ── */}
      <HeroBanner dateLabel={`Today, ${todayLabel}`} onStartReview={() => navigate("/learners")} />

      {/* ── Alerts row — one StatCard per STAT_CARDS entry ── */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {STAT_CARDS.map(({ key, title, subtitle }) => {
          const count = stats?.[key] ?? 0;
          return (
            <StatCard
              key={key}
              title={title}
              subtitle={subtitle(count)}
              trailing={<span className="text-lg font-extrabold text-brand-fg">{count}</span>}
            />
          );
        })}
      </div>

      {/* ── Calendar (left) + task panel (right) ── */}
      {/* .main-layout sets its own fixed height — no flex-1, so it does not
          stretch to the viewport */}
      <div className="main-layout">
        {/* Calendar — capped width so the square day cells stay a sensible size */}
        <div className="w-full max-w-[460px]">
          <Calendar events={events} />
        </div>

        {/* Task panel — takes the remaining width */}
        <div className="flex min-w-[320px] flex-1 flex-col gap-4 overflow-y-auto">
          <TaskList title="Today's Tasks" tasks={tasks.today} />
          <TaskList title="Upcoming"      tasks={tasks.upcoming} />
        </div>
      </div>

      {/* ── Cohort skills comparison ── */}
      <div>
        <h2 className="mb-3 text-[15px] font-semibold text-brand-fg">
          Cohort Skills Comparison
        </h2>
        <Graph onSelectLearner={setSelectedLearner} />
      </div>

      {/* Same LearnerDetailPage the Learners tab routes to, handed an id instead of
          reading one from the URL. Closing returns to the graph with its selected
          cluster and camera angle intact.

          Every plotted learner can be opened: since the merge they are all rows in `learners`
          with a uuid. A research-cohort learner's page renders read-only — the page decides
          that from `on_caseload`, not this component. */}
      {selectedLearner && (
        <Modal onClose={() => setSelectedLearner(null)}>
          <LearnerDetailPage
            learnerId={selectedLearner.id}
            onBack={() => setSelectedLearner(null)}
          />
        </Modal>
      )}
    </div>
  );
}
