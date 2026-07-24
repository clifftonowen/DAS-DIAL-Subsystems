// StatCard.jsx — Alert/summary tile on the Main page.
// Pure presentational — no state, no data fetching.
//
// Props:
//   icon     {string}  — emoji icon e.g. "⚠️"
//   iconBg   {string}  — Tailwind bg class for icon circle e.g. "bg-red-100"
//   title    {string}  — bold card title
//   subtitle {string}  — descriptive line below title
//   trailing {node}    — right-aligned element (count number or badge)

export default function StatCard({ icon, iconBg, title, subtitle, trailing }) {
  return (
    // Matches prototype .alert-card — white card, horizontal flex, border
    <div className="flex items-center gap-4 rounded-xl border border-brand-border
                    bg-white p-4 shadow-sm">
      {/* Coloured icon circle */}
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center
                       rounded-full text-xl ${iconBg}`}>
        {icon}
      </div>

      {/* Text content — title + subtitle */}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-brand-fg">{title}</p>
        <p className="text-xs text-brand-fg-muted">{subtitle}</p>
      </div>

      {/* Right-aligned count or badge — passed in by parent */}
      <div className="shrink-0">{trailing}</div>
    </div>
  );
}
