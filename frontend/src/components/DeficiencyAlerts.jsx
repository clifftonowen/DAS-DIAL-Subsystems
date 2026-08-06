// DeficiencyAlerts.jsx — the DIAL marks a learner is furthest behind on.
//
// FLAGS ON PERCENTILE, NOT THE RAW MARK. The four rubrics are not comparable to each other —
// phonics is out of 46 and word reading out of 10 — so a raw threshold would flag word reading
// for almost everyone and phonics for almost nobody. The percentile ranks each mark within the
// learner's own band group, which is the only figure that means the same thing across all four.
//
// AN UNASSESSED METRIC IS NEVER FLAGGED. Writing is not administered to band A at all, so a
// missing mark is the norm, not a deficiency — calling it one would put an alert on the page
// for a paper the learner was never given.
//
// Props:
//   metrics {Array} [{ key, label, raw, max, percentile, assessed }] from the overview endpoint

// Below this percentile, a metric is worth the therapist's attention. 50 is the median of the
// learner's own band group — "behind more than half the learners who sat the same paper".
const CONCERN = 50;
const CRITICAL = 15;
const LOW = 30;
const MAX_SHOWN = 4;

const ordinal = (value) => {
  const n = Math.round(value);
  const suffix = n % 100 >= 11 && n % 100 <= 13
    ? "th"
    : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return `${n}${suffix}`;
};

export default function DeficiencyAlerts({ metrics = [] }) {
  const deficiencies = metrics
    .filter((m) => m.assessed && m.percentile < CONCERN)
    .sort((a, b) => a.percentile - b.percentile)
    .slice(0, MAX_SHOWN);

  if (deficiencies.length === 0) {
    return (
      <div className="mb-5 text-sm italic text-brand-fg-muted">
        {metrics.some((m) => m.assessed)
          ? "No metric falls below the median of this learner's band."
          : "No assessment scores to compare yet."}
      </div>
    );
  }

  return (
    <div className="mb-5 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
      {deficiencies.map((metric) => {
        const isCritical = metric.percentile < CRITICAL;
        const isLow = metric.percentile >= CRITICAL && metric.percentile < LOW;

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
            key={metric.key}
            className={`flex items-center gap-3 rounded-r-xl border border-l-0 border-brand-border p-3.5 ${severityClass}`}
          >
            <div>
              <div className="text-[13px] font-semibold text-brand-fg">{metric.label}</div>
              <div className="mt-0.5 flex items-center gap-1.5 text-xs text-brand-fg-muted">
                {/* Both numbers: the rank is why it is flagged, the mark is what was awarded. */}
                {metric.raw}/{metric.max} · {ordinal(metric.percentile)} pct
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${badgeClass}`}>
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
