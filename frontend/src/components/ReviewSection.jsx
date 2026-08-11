// ReviewSection.jsx — reviews for the latest activity on LearnerDetailPage
//
// The therapist writes a comment and chooses one of three actions:
//
//   Approve       comment + record the therapist decision APPROVED
//   Not approved  comment + record the therapist decision REJECTED
//   Upload        comment only, verdict left open
//
// Props:
//   activityId    {string} the activity being reviewed

import { useEffect, useState } from "react";
import Button from "./Button";
import { getReviews, submitReview } from "../lib/api";

const VERDICT_LABEL = {
  APPROVED: "Therapist approved",
  REJECTED: "Therapist rejected",
};

const VERDICT_STYLE = {
  APPROVED: "bg-green-50 text-green-700",
  REJECTED: "bg-red-50 text-red-700",
};

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString();
}

function reviewerLabel(review) {
  return review.reviewer?.name?.trim()
    || review.reviewer?.email
    || review.reviewer?.id
    || review.therapist_id
    || "Unknown reviewer";
}

export default function ReviewSection({ activityId }) {
  const [reviews, setReviews] = useState([]);
  const [text, setText] = useState("");
  const [approvalStatus, setApprovalStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(null);   
  const [error, setError] = useState(null);

  useEffect(() => {
    // `cancelled` guards against the therapist switching activities before this
    // resolves — without it a slow response would overwrite the newer list.
    let cancelled = false;

    async function load() {
      setLoading(true);
      setApprovalStatus(null);
      try {
        const data = await getReviews(activityId);
        if (!cancelled) {
          const loaded = data ?? [];
          setReviews(loaded);
          setApprovalStatus(
            loaded.find((review) => review.approval_status)?.approval_status ?? null,
          );
        }
      } catch (err) {
        console.error("Could not load reviews", err);
        if (!cancelled) setReviews([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [activityId]);

  const decided = approvalStatus === "APPROVED" || approvalStatus === "REJECTED";
  const busy = pending !== null;

  async function submit(verdict) {
    const body = text.trim();
    if (!body) return;

    setPending(verdict ?? "COMMENT");
    setError(null);
    try {
      const saved = await submitReview(activityId, body, verdict);
      setReviews((prev) => [saved, ...prev]);   
      setText("");
      if (verdict) {
        setApprovalStatus(verdict);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="rounded-xl border border-brand-border bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <label htmlFor="review-text" className="text-sm font-medium text-brand-fg">
          Leave a review
        </label>
        {decided && (
          <span className={`rounded px-2 py-0.5 text-xs font-semibold ${VERDICT_STYLE[approvalStatus]}`}>
            {VERDICT_LABEL[approvalStatus]}
          </span>
        )}
      </div>

      <textarea
        id="review-text"
        rows={3}
        value={text}
        disabled={busy}
        onChange={(e) => {
          setText(e.target.value);
          if (error) setError(null);
        }}
        placeholder="How did this activity work for the learner?"
        className={`mt-1.5 w-full resize-y rounded-lg border-2 px-3 py-2 text-sm outline-none transition-colors
          disabled:bg-brand-muted disabled:text-brand-fg-muted
          ${error ? "border-red-400 focus:border-red-500" : "border-brand-border focus:border-brand-primary"}`}
      />

      {error && (
        <div role="alert" className="mt-2 rounded-lg border border-red-200 bg-red-50 p-3">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {decided && (
        <p className="mt-2 text-xs text-brand-fg-muted">
          The therapist decision is final, but you can still add a comment.
        </p>
      )}

      <div className="mt-3 flex flex-wrap justify-end gap-2.5">
        <Button variant="ghost" onClick={() => submit(null)}
                loading={pending === "COMMENT"} disabled={busy || !text.trim()}>
          Upload
        </Button>
        <Button variant="secondary" onClick={() => submit("REJECTED")}
                loading={pending === "REJECTED"} disabled={busy || decided || !text.trim()}>
          Not approved
        </Button>
        <Button variant="primary" onClick={() => submit("APPROVED")}
                loading={pending === "APPROVED"} disabled={busy || decided || !text.trim()}>
          Approve
        </Button>
      </div>

      <div className="mt-5 border-t border-brand-border pt-4">
        {loading ? (
          <p className="text-sm text-brand-fg-muted">Loading reviews…</p>
        ) : reviews.length === 0 ? (
          <p className="text-sm text-brand-fg-muted">No reviews yet.</p>
        ) : (
          <ul className="space-y-3">
            {reviews.map((review, index) => (
              <li key={review.id ?? index} className="rounded-lg bg-brand-muted p-3">
                <p className="whitespace-pre-wrap text-sm text-brand-fg">{review.text}</p>
                <p className="mt-1.5 text-xs text-brand-fg-muted">
                  {reviewerLabel(review)}
                  {formatDate(review.created_at) && ` · ${formatDate(review.created_at)}`}
                  {review.approval_status && ` · ${VERDICT_LABEL[review.approval_status]}`}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
