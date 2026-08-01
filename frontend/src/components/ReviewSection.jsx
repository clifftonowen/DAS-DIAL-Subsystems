// ReviewSection.jsx — the Dashboard
//
// The therapist writes a comment and chooses one of three actions:
//
//   Approve       comment + mark the activity VALIDATED
//   Not approved  comment + mark it FLAGGED
//   Upload        comment only, verdict left open
//
// Props:
//   activityId    {string} the activity being reviewed
//   initialStatus {string} its status when the page loaded, if known
//   onStatusChange{func}   called with the new status after a verdict lands

import { useEffect, useState } from "react";
import Button from "./Button";
import { getReviews, submitReview } from "../lib/api";

const VERDICT_LABEL = {
  VALIDATED: "Approved",
  FLAGGED: "Not approved",
};

const VERDICT_STYLE = {
  VALIDATED: "bg-green-50 text-green-700",
  FLAGGED: "bg-red-50 text-red-700",
};

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString();
}

export default function ReviewSection({ activityId, initialStatus = null, onStatusChange }) {
  const [reviews, setReviews] = useState([]);
  const [text, setText] = useState("");
  const [status, setStatus] = useState(initialStatus);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(null);   
  const [error, setError] = useState(null);

  useEffect(() => setStatus(initialStatus), [initialStatus, activityId]);

  useEffect(() => {
    // `cancelled` guards against the therapist switching activities before this
    // resolves — without it a slow response would overwrite the newer list.
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const data = await getReviews(activityId);
        if (!cancelled) setReviews(data ?? []);
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

  const decided = status === "VALIDATED" || status === "FLAGGED";
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
        setStatus(verdict);
        onStatusChange?.(verdict);
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
          <span className={`rounded px-2 py-0.5 text-xs font-semibold ${VERDICT_STYLE[status]}`}>
            {VERDICT_LABEL[status]}
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
          This activity has been marked {VERDICT_LABEL[status].toLowerCase()}. That decision is
          final, but you can still add a comment.
        </p>
      )}

      <div className="mt-3 flex flex-wrap justify-end gap-2.5">
        <Button variant="ghost" onClick={() => submit(null)}
                loading={pending === "COMMENT"} disabled={busy || !text.trim()}>
          Upload
        </Button>
        <Button variant="secondary" onClick={() => submit("FLAGGED")}
                loading={pending === "FLAGGED"} disabled={busy || decided || !text.trim()}>
          Not approved
        </Button>
        <Button variant="primary" onClick={() => submit("VALIDATED")}
                loading={pending === "VALIDATED"} disabled={busy || decided || !text.trim()}>
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
                {formatDate(review.created_at) && (
                  <p className="mt-1.5 text-xs text-brand-fg-muted">
                    {formatDate(review.created_at)}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}