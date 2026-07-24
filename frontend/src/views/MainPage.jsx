// MainPage.jsx — Default landing page rendered at route "/".
//
// Layout matches the prototype's .main-layout grid (defined in index.css):
//   .main-alerts  — full-width row of 4 StatCards at the top
//   left column   — Calendar
//   right column  — TaskList (Today's Tasks + Upcoming)
//
// All data is hardcoded to match the prototype exactly.
// When real data is available, replace the static arrays with API calls.

import { useState, useEffect } from "react";
import StatCard from "../components/StatCard";
import Calendar from "../components/Calendar";
import TaskList from "../components/TaskList";
import { getDashboardStats, getDashboardTasks, getDashboardEvents } from "../lib/api";

export default function MainPage() {
  const [stats, setStats] = useState(null);
  const [tasks, setTasks] = useState({ today: [], upcoming: [] });
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

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

  const statCards = [
    {
      icon: "⚠️",
      iconBg: "bg-red-100",
      title: "Flagged Activities",
      subtitle: `${stats?.flagged || 0} activities need your review`,
      trailing: <span className="text-lg font-bold text-brand-fg">{stats?.flagged || 0}</span>,
    },
    {
      icon: "📊",
      iconBg: "bg-yellow-100",
      title: "Needs Profiling",
      subtitle: `${stats?.needs_profiling || 0} learners missing a profile`,
      trailing: <span className="text-lg font-bold text-brand-fg">{stats?.needs_profiling || 0}</span>,
    },
    {
      icon: "🔴",
      iconBg: "bg-red-100",
      title: "High Risk",
      subtitle: `${stats?.high_risk || 0} learners with high risk`,
      trailing: (
        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
          Urgent
        </span>
      ),
    },
    {
      icon: "📅",
      iconBg: "bg-blue-100",
      title: "Inactive Learners",
      subtitle: `${stats?.inactive || 0} learner inactive 30+ days`,
      trailing: <span className="text-lg font-bold text-brand-fg">{stats?.inactive || 0}</span>,
    }
  ];

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-brand-border border-t-brand-primary"></div>
      </div>
    );
  }

  return (
    <div className="main-layout h-full">
      {/* ── Alerts row ── */}
      <div className="main-alerts grid grid-cols-2 gap-3 xl:grid-cols-4">
        {statCards.map((card) => (
          <StatCard key={card.title} {...card} />
        ))}
      </div>

      {/* ── Calendar — left column ── */}
      <Calendar events={events} />

      {/* ── Task panel — right column ── */}
      <div className="flex flex-col gap-4 overflow-y-auto">
        <TaskList title="📋 Today's Tasks" tasks={tasks.today} />
        <TaskList title="📌 Upcoming"       tasks={tasks.upcoming} />
      </div>
    </div>
  );
}
