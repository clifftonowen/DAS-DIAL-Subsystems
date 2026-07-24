// DeficiencyAlerts.jsx — Renders a row of alert cards for skills scoring below 50.
// Matches the prototype's deficiency-alerts section.
//
// Props:
//   skills {Object} — mapping of skill keys to scores (0-100)

import { SKILL_LABELS } from "../lib/constants";

export default function DeficiencyAlerts({ skills }) {
  // Find skills < 50, sort ascending (worst first), take top 4
  const deficiencies = Object.entries(skills)
    .filter(([_, val]) => val < 50)
    .sort((a, b) => a[1] - b[1])
    .slice(0, 4);

  if (deficiencies.length === 0) {
    return (
      <div className="text-sm text-brand-fg-muted italic mb-5">
        No critical deficiencies detected.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3 mb-5">
      {deficiencies.map(([key, val]) => {
        // Determine severity and styling based on score
        const isCritical = val < 30;
        const isLow = val >= 30 && val < 40;
        
        const severityClass = isCritical
          ? "deficiency-high bg-red-50"
          : isLow
          ? "deficiency-medium bg-orange-50"
          : "deficiency-low bg-blue-50";

        const badgeClass = isCritical
          ? "bg-red-100 text-red-700"
          : isLow
          ? "bg-orange-100 text-orange-700"
          : "bg-blue-100 text-blue-700";

        const severityLabel = isCritical ? "Critical" : isLow ? "Low" : "Below Average";

        return (
          <div
            key={key}
            className={`flex items-center gap-3 p-3.5 rounded-r-xl border border-brand-border border-l-0 ${severityClass}`}
          >
            <div>
              <div className="text-[13px] font-semibold text-brand-fg">
                {SKILL_LABELS[key] || key}
              </div>
              <div className="mt-0.5 text-xs text-brand-fg-muted flex items-center gap-1.5">
                Score: {val}/100 · 
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${badgeClass}`}>
                  {severityLabel}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
