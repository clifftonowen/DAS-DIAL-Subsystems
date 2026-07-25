// Calendar.jsx — Interactive monthly calendar with event dot indicators.
// Matches the prototype calendar widget.
//
// Props:
//   events  {string[]}  — array of "YYYY-MM-DD" date strings that have events
//                         e.g. ["2026-07-03", "2026-07-14"]
//
// Internal state:
//   year, month — controlled with ‹ / › nav buttons

import { useState } from "react";

// Day-of-week headers, Mon-first to match the prototype
const DAY_HEADERS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function Calendar({ events = [] }) {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth()); // 0-indexed

  // ── Month navigation ──────────────────────────────────────────────
  function prevMonth() {
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else setMonth(m => m - 1);
  }
  function nextMonth() {
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else setMonth(m => m + 1);
  }

  // ── Date calculations ─────────────────────────────────────────────
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  // getDay() returns 0=Sun..6=Sat; convert to Mon-first offset (0=Mon..6=Sun)
  const rawFirstDay = new Date(year, month, 1).getDay();
  const firstDayOffset = (rawFirstDay + 6) % 7; // Mon-first

  // Build array of day numbers, with null for empty leading cells
  const cells = [
    ...Array(firstDayOffset).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  // Set of event day numbers for quick lookup
  const eventDays = new Set(
    events
      .filter(d => {
        const dt = new Date(d);
        return dt.getFullYear() === year && dt.getMonth() === month;
      })
      .map(d => new Date(d).getDate())
  );

  const monthLabel = new Date(year, month).toLocaleDateString("en-SG", {
    month: "long", year: "numeric",
  });

  // ── Render ────────────────────────────────────────────────────────
  return (
    <div className="flex h-full flex-col rounded-2xl border border-brand-border bg-white p-[18px] shadow-sm">

      {/* ── Header: title + nav buttons ── */}
      <div className="mb-3.5 flex items-center justify-between">
        <p className="text-sm font-semibold text-brand-fg">Calendar</p>
        <div className="flex items-center gap-2">
          <button
            onClick={prevMonth}
            className="rounded px-2 py-0.5 text-brand-fg-muted hover:bg-brand-muted"
            aria-label="Previous month"
          >‹</button>
          <span className="min-w-[110px] text-center text-xs font-medium text-brand-fg">
            {monthLabel}
          </span>
          <button
            onClick={nextMonth}
            className="rounded px-2 py-0.5 text-brand-fg-muted hover:bg-brand-muted"
            aria-label="Next month"
          >›</button>
        </div>
      </div>

      {/* ── Day-of-week headers ── */}
      {/* .calendar-grid defined in index.css: 7-column equal grid */}
      <div className="calendar-grid mb-1">
        {DAY_HEADERS.map(d => (
          <div key={d} className="py-1 text-center text-[10px] font-semibold
                                  uppercase tracking-[0.06em] text-brand-fg-muted">
            {d}
          </div>
        ))}
      </div>

      {/* ── Day cells ── */}
      <div className="calendar-grid flex-1">
        {cells.map((day, idx) => {
          if (day === null) return <div key={`empty-${idx}`} />;

          const isToday =
            day === today.getDate() &&
            month === today.getMonth() &&
            year === today.getFullYear();
          const hasEvent = eventDays.has(day);

          return (
            // .cal-day defined in index.css: aspect-ratio:1, min-height:48px
            <div
              key={day}
              className={[
                "cal-day relative flex flex-col items-center justify-center rounded-[10px]",
                "text-xs font-medium transition-colors",
                isToday
                  ? "bg-brand-primary font-bold text-white"
                  : "text-brand-fg hover:bg-brand-muted",
              ].join(" ")}
            >
              {day}
              {/* Event dot — shown below the day number */}
              {hasEvent && !isToday && (
                <span className="absolute bottom-[5px] h-1 w-1 rounded-full bg-brand-primary" />
              )}
              {hasEvent && isToday && (
                <span className="absolute bottom-[5px] h-1 w-1 rounded-full bg-white/80" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
