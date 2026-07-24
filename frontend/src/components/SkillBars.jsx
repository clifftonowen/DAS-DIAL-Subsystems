// SkillBars.jsx — Renders a list of progress bars for each cognitive skill.
// Matches the prototype's Progress & Activity card.
//
// Props:
//   skills {Object} — mapping of skill keys to scores (0-100)

import { SKILL_LABELS, SKILL_COLORS } from "../lib/constants";

export default function SkillBars({ skills }) {
  // Sort keys to have a consistent order or just use the keys from SKILL_LABELS
  const keys = Object.keys(SKILL_LABELS);

  return (
    <div className="flex flex-col gap-3.5">
      {keys.map((k) => {
        const val = skills[k] || 0;
        
        // Compute status from value (prototype used static status fields, 
        // but in real app we'll compute it dynamically)
        let statusLabel = "Not started";
        let tagClass = "bg-gray-100 text-gray-700";
        if (val >= 60) {
          statusLabel = "Worked on";
          tagClass = "bg-green-100 text-green-700";
        } else if (val >= 35) {
          statusLabel = "Needs work";
          tagClass = "bg-orange-100 text-orange-700";
        }

        return (
          <div key={k} className="flex flex-col">
            {/* ── Header: Label + Value ── */}
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-xs font-semibold text-brand-fg">
                {SKILL_LABELS[k]}
              </span>
              <span className="text-xs font-semibold text-brand-fg-muted">
                {val}%
              </span>
            </div>

            {/* ── Progress Track + Fill ── */}
            <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-brand-muted">
              <div
                className="skill-bar-fill h-full rounded-full"
                style={{ width: `${val}%`, backgroundColor: SKILL_COLORS[k] }}
              />
            </div>

            {/* ── Status Tag ── */}
            <div className="mt-1.5">
              <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${tagClass}`}>
                {statusLabel}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
