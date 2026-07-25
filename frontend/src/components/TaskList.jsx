// TaskList.jsx — Checklist panel with toggleable task items.
// Matches the prototype's .task-card widgets (Today's Tasks + Upcoming).
//
// Props:
//   title  {string}     — section heading e.g. "Today's Tasks"
//   tasks  {Array}      — array of { text: string, meta: string, done?: boolean }
//
// Internal state:
//   items — copy of props.tasks so checkbox toggles work without lifting state

import { useState } from "react";

export default function TaskList({ title, tasks = [] }) {
  // Copy into local state so toggles are self-contained
  const [items, setItems] = useState(tasks);

  function toggle(index) {
    setItems(prev =>
      prev.map((item, i) =>
        i === index ? { ...item, done: !item.done } : item
      )
    );
  }

  return (
    <div className="rounded-2xl border border-brand-border bg-white p-4 shadow-sm">
      {/* ── Section title ── */}
      <p className="mb-3 text-sm font-semibold text-brand-fg">{title}</p>

      {/* ── Task items ──
          Capped at five rows, then scrolls: 5 × 36px (13px title + 11px meta)
          + 4 × 12px space-y gap = 228px. A task whose text wraps is taller, so
          a long one shows four and a bit — the cap is a height, not a count. */}
      <div className="max-h-[228px] space-y-3 overflow-y-auto pr-1">
        {items.map((item, i) => (
          <div key={i} className="flex items-start gap-3">
            {/* ── Checkbox circle — toggles done state on click ── */}
            <button
              onClick={() => toggle(i)}
              aria-label={item.done ? "Mark incomplete" : "Mark complete"}
              className={[
                "mt-0.5 h-5 w-5 shrink-0 rounded-full border-2 transition-all",
                item.done
                  ? "border-brand-success bg-brand-success"  // filled green when done
                  : "border-brand-border bg-white",           // empty circle when pending
              ].join(" ")}
            />

            {/* ── Task text + meta ── */}
            <div>
              <p className={[
                "text-[13px] font-medium transition-colors",
                item.done ? "text-brand-fg-muted line-through" : "text-brand-fg",
              ].join(" ")}>
                {item.text}
              </p>
              <p className="text-[11px] text-brand-fg-muted">{item.meta}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
