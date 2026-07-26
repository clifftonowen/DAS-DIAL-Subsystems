// ProfileRadarChart.jsx — Renders a radar chart for the cognitive profile using recharts.
// Matches the prototype's Cognitive Profile card.
//
// Props:
//   skills {Object} — mapping of skill keys to scores (0-100)

import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer } from "recharts";
import { SKILL_LABELS, SKILL_COLORS } from "../lib/constants";

export default function ProfileRadarChart({ skills }) {
  // Format data for Recharts
  const data = Object.keys(SKILL_LABELS).map((k) => ({
    subject: SKILL_LABELS[k].split(" ")[0], // Use first word for brevity on chart
    fullLabel: SKILL_LABELS[k],
    score: skills[k] || 0,
    color: SKILL_COLORS[k],
  }));

  return (
    <div className="flex flex-col h-full">
      {/* ── Chart Container ── */}
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
            <PolarGrid stroke="#EAECEF" />
            <PolarAngleAxis
              dataKey="subject"
              tick={{ fill: "#6B727D", fontSize: 10, fontWeight: 500 }}
            />
            {/* The radar polygon — brand primary colour with low opacity fill */}
            <Radar
              name="Student"
              dataKey="score"
              stroke="#FF2E45"
              strokeWidth={2}
              fill="#FF2E45"
              fillOpacity={0.12}
            />
            {/* Note: we can't easily do per-dot colors with standard Radar, 
                so we use the legend to show the distinct colors */}
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* ── Legend ── */}
      <div className="mt-4 grid grid-cols-2 gap-2 text-[11px] font-medium text-brand-fg-muted sm:grid-cols-3">
        {data.map((item) => (
          <div key={item.subject} className="flex items-center gap-1.5">
            <div 
              className="h-2 w-2 shrink-0 rounded-full" 
              style={{ backgroundColor: item.color }} 
            />
            <span>{item.fullLabel}: {item.score}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
