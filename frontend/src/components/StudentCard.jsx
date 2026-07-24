// StudentCard.jsx — Presentational component for a learner card.
// Matches the prototype's .student-card styles.
//
// Props:
//   student  {Object}    — learner data object (name, band, tier, color, initial)
//   onClick  {Function}  — handler when card is clicked (e.g. to navigate)

export default function StudentCard({ student, onClick }) {
  return (
    <div
      onClick={onClick}
      // Corresponds to .student-card and .student-card:hover in prototype
      className="flex cursor-pointer flex-col items-center gap-2.5 rounded-xl border border-brand-border bg-white px-4 py-5 transition-all duration-150 hover:-translate-y-0.5 hover:border-brand-primary hover:shadow-md"
    >
      {/* ── Avatar Circle ── */}
      <div
        className="flex h-16 w-16 items-center justify-center rounded-full border-2 bg-brand-muted text-2xl font-semibold overflow-hidden"
        style={{ borderColor: student.color, color: student.color }}
      >
        {student.initial}
      </div>
      
      {/* ── Name and Meta ── */}
      <div className="text-sm font-semibold text-brand-fg text-center">{student.name}</div>
      <div className="text-xs text-brand-fg-muted text-center">
        {student.band} · {student.tier}
      </div>
    </div>
  );
}
