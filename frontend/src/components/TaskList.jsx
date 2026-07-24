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
    <div className="rounded-xl border border-brand-border bg-white p-4 shadow-sm">
      {/* ── Section title ── */}
      <p className="mb-3 text-sm font-semibold text-brand-fg">{title}</p>

      {/* ── Task items ── */}
      <div className="space-y-3">
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
                "text-sm font-medium transition-colors",
                item.done ? "text-brand-fg-muted line-through" : "text-brand-fg",
              ].join(" ")}>
                {item.text}
              </p>
              <p className="text-xs text-brand-fg-muted">{item.meta}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
