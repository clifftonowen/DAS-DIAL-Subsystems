// ReviewSection.jsx — the Dashboard 
// Upload, and see it appear in the list ("display review alongside the
// activity"). Existing reviews are loaded on mount so the postcondition —
// stored *and* displayed — holds across a page refresh, not just right after
// submitting.
//
// The therapist id is never sent. ReviewController resolves it from the
// session, which is the diagram's "resolve therapistId from session" self-call.
//
// Props:
//   activityId {string} — the activity being reviewed

import { useEffect, useState } from "react";
import Button from "./Button";
import { getReviews, submitReview } from "../lib/api";

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString();
}

export default function ReviewSection({ activityId }) {
  const [reviews, setReviews] = useState([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const data = await getReviews(activityId);
        if (!cancelled) setReviews(data ?? []);
      } catch (err) {
        // Failing to read reviews must not hide the form — the therapist can
        // still leave one.
        console.error("Could not load reviews", err);
        if (!cancelled) setReviews([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [activityId]);

  async function handleUpload(e) {
    e.preventDefault();
    const body = text.trim();
    if (!body) return;

    setSubmitting(true);
    setError(null);
    try {
      const saved = await submitReview(activityId, body);
      // Step 6. Prepend, because the API returns newest-first.
      setReviews((prev) => [saved, ...prev]);
      setText("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-xl border border-brand-border bg-white p-5 shadow-sm">
      <form onSubmit={handleUpload}>
        <label htmlFor="review-text" className="block text-sm font-medium text-brand-fg">
          Leave a review
        </label>
        <textarea
          id="review-text"
          rows={3}
          value={text}
          disabled={submitting}
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

        <div className="mt-3 flex justify-end">
          <Button type="submit" variant="primary" loading={submitting}
                  disabled={submitting || !text.trim()}>
            {submitting ? "Uploading…" : "Upload"}
          </Button>
        </div>
      </form>

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