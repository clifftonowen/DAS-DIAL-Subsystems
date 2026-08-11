// ActivityReviewPanel.jsx — shows the last generated activity and its verdict.
//
// Props:
//   activity {object} a learning_activities row (content, status, ...)

import ActivityContent from "./ActivityContent";

// UC3's AUTOMATED verdict, which is not the therapist's. The ValidativeAgent checked the draft
// against the DAS framework and the curriculum it was grounded in; a human has still approved
// nothing at this point — that decision is UC4's, lives on `reviews.approval_status`, and renders
// separately in ReviewSection. These read "Validated"/"Flagged", never "Approved", so the two
// claims stay distinguishable on screen the way they are in the schema.
const STATUS_LABEL = {
  VALIDATED: "Validated",
  FLAGGED: "Flagged for review",
  GENERATED: "Not yet reviewed",
};

const STATUS_STYLE = {
  VALIDATED: "bg-green-50 text-green-700",
  FLAGGED: "bg-red-50 text-red-700",
  GENERATED: "bg-gray-100 text-gray-700",
};

export default function ActivityReviewPanel({ activity }) {
  // Older rows may carry no status at all; treat those as not yet reviewed.
  const status = activity.status || "GENERATED";

  return (
    <div className="overflow-hidden rounded-xl border border-brand-border bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand-border bg-brand-muted/50 px-6 py-3">
        <div>
          <p className="text-sm font-semibold text-brand-fg">Last generated activity</p>
          {activity.literacy_objective && (
            <p className="text-xs text-brand-fg-muted">{activity.literacy_objective}</p>
          )}
        </div>
        <span className={`rounded px-2.5 py-1 text-xs font-semibold ${STATUS_STYLE[status] ?? STATUS_STYLE.GENERATED}`}>
          {STATUS_LABEL[status] ?? status}
        </span>
      </div>
      <div className="px-6 py-5">
        <ActivityContent text={activity.content?.text ?? ""} />
      </div>
    </div>
  );
}