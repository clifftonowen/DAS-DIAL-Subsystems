// LearnerDetailPage.jsx — Detailed view for a specific learner.
//
// Used two ways, from one copy of the code:
//   - as the route "/learners/:id" inside the Dashboard shell (the Learners tab)
//   - inside a Modal on MainPage, opened from the cohort graph's cluster table
//
// Displays the learner's header, deficiency alerts, the DIAL radar chart of their current
// marks, and a line chart of those marks across every semester on record.
//
// Props — both optional, and both undefined when this is used as a route, so the
// routed behaviour is unchanged:
//   learnerId {string}   which learner to show, when the URL carries no :id
//   onBack    {function} replaces the back-to-learners navigation, so the embedded
//                        copy closes its overlay instead of navigating away

import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Button from "../components/Button";
import DeficiencyAlerts from "../components/DeficiencyAlerts";
import ProfileRadarChart from "../components/ProfileRadarChart";
import ScoreHistoryChart from "../components/ScoreHistoryChart";
import ShareWindow from "../components/ShareWindow";
import ActivityReviewPanel from "../components/ActivityReviewPanel";
import GroundingSources from "../components/GroundingSources";
import ReviewSection from "../components/ReviewSection";
import UploadView from "./UploadView";
import {
  getLearner, generateProfile, generateActivity, getLearnerActivities, getLearnerOverview,
} from "../lib/api";

export default function LearnerDetailPage({ learnerId, onBack }) {
  const { id: routeId } = useParams();
  const navigate = useNavigate();

  // Prop wins when embedded; the route param is the only source when routed. The
  // merged value keeps the name `id`, so nothing downstream changes.
  const id = learnerId ?? routeId;
  const goBack = onBack ?? (() => navigate("/learners"));
  const backLabel = onBack ? "← Close" : "← Back to Learners";

  const [student, setStudent] = useState(null);
  // Everything measured, from GET /learners/{id}/overview: `metrics` are the learner's CURRENT
  // marks (the radar chart and the deficiency alerts) and `history` is every sitting on record,
  // oldest first (the line chart). Both can be empty — a learner added in the app has no scores
  // until an assessment is uploaded for them.
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [latestActivity, setLatestActivity] = useState(null);
  const [isSharing, setIsSharing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  // Activity generation, which happens HERE now rather than on a page of its own.
  // `notes` steers retrieval — it is appended to the query built from the learner's marks, so
  // it changes which curriculum chunks come back, not just how the activity is labelled.
  // `activityResult` holds only a FAILURE (a refusal or a thrown error); a success clears it,
  // because the outcome of a success is the new activity itself.
  const [notes, setNotes] = useState("");
  const [isGeneratingActivity, setIsGeneratingActivity] = useState(false);
  const [activityResult, setActivityResult] = useState(null);

  // Just the activities. Separate from loadData because regenerating must not flip `loading`,
  // which would replace the whole page with the spinner for the length of an LLM call.
  async function refreshActivities() {
    const activities = await getLearnerActivities(id);
    setLatestActivity(activities?.[0] ?? null);
  }

  async function loadData() {
    setLoading(true);
    try {
      const learnerData = await getLearner(id);

      // A research-cohort learner is anonymised: no pseudonym, no tier. Their workbook id is
      // the only name they have, and the badge says what they are instead of inventing a tier.
      const name = learnerData.pseudonym || learnerData.student_id || "Unknown";
      const formattedLearner = {
        ...learnerData,
        name,
        band: learnerData.band || (learnerData.band_group ? `Band ${learnerData.band_group}` : "—"),
        tier: learnerData.tier || (learnerData.on_caseload ? "Tier 2" : "DAS research cohort"),
        initial: name.charAt(0).toUpperCase(),
        color: ['#FF2E45', '#FFCA28', '#2563EB', '#22A06B', '#7C3AED'][Math.floor(Math.random() * 5)]
      };
      setStudent(formattedLearner);

      // Activities hang off the learner now, not a separate profile row.
      await refreshActivities();

      // Not fatal: a learner with no scores still has a page, and it shows the upload prompt.
      try {
        setOverview(await getLearnerOverview(id));
      } catch (overviewErr) {
        console.error("Failed to load DIAL assessment", overviewErr);
        setOverview(null);
      }
    } catch (err) {
      console.error("Failed to load learner details", err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [id]);

  // Promotes the learner's most recent sitting to their current marks. A 409 means they have
  // no scores at all, which is not a failure the therapist can retry out of — it is the cue to
  // upload one, so it opens the upload flow rather than showing them an error.
  const handleGenerateProfile = async () => {
    setIsGenerating(true);
    try {
      await generateProfile(id);
      await loadData();
    } catch (err) {
      if (String(err.message).toLowerCase().includes("no assessment scores")) {
        setIsUploading(true);
      } else {
        alert("Failed to generate profile: " + err.message);
      }
    } finally {
      setIsGenerating(false);
    }
  };

  // Generate a fresh activity for this learner, replacing the one on screen.
  //
  // THE RESULT IS NOT RENDERED DIRECTLY. It carries no activity id, and its `content` is a bare
  // string where a stored row's is an object — so the page re-reads the activity list instead
  // and takes the newest row. That gives one shape everywhere, and an id, which ReviewSection
  // and ShareWindow both need to work on the activity that was just made.
  //
  // A refusal is not a failure of the request: the backend returns 200 with a reason, because
  // the curriculum genuinely does not cover this learner's need. The previous activity stays on
  // screen — replacing it with an error would lose work the therapist may still be using.
  const handleGenerateActivity = async () => {
    setIsGeneratingActivity(true);
    setActivityResult(null);
    try {
      const result = await generateActivity(id, { notes: notes.trim() });
      // TESTED AGAINST THE REFUSAL, NOT AGAINST THE SUCCESS STATUSES. This used to read
      // `=== "GENERATED"`, which silently stopped being true when UC3 gained its validate loop:
      // the backend now returns VALIDATED or FLAGGED, so a successful generation fell to the
      // else branch, the list was never re-read, and the therapist watched the spinner stop with
      // nothing on screen and no error. INSUFFICIENT_CONTEXT is the only status that means no row
      // was written, so keying on it is what stays correct when the status set grows again.
      if (result.status === "INSUFFICIENT_CONTEXT") {
        setActivityResult(result);
      } else {
        await refreshActivities();
      }
    } catch (err) {
      console.error("Failed to generate activity", err);
      setActivityResult({ error: err.message });
    } finally {
      setIsGeneratingActivity(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-brand-border border-t-brand-primary"></div>
      </div>
    );
  }

  // Whether this learner is one of the therapist's own. INFORMATIONAL ONLY — it drives a badge,
  // not what the page lets you do. Every learner's profile is now just their DIAL marks, so
  // every learner can be profiled, have an activity generated, and be shared.
  const isCaseload = Boolean(overview?.on_caseload);
  const metrics = overview?.metrics ?? [];
  const history = overview?.history ?? [];
  const hasScores = metrics.some((m) => m.assessed);

  // A refusal comes back 200 with a status, not as a thrown error — the request succeeded, the
  // corpus just did not cover this learner. An EMPTY QUERY is the separate signal that they have
  // no marks to steer with at all: build_query returns "" when no metric has a mark and the
  // therapist left the focus blank, and the gate then refuses rather than letting the LLM invent.
  const refused = activityResult?.status === "INSUFFICIENT_CONTEXT";
  const noScores = refused && !activityResult.query;

  if (error || !student) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-brand-fg-muted">Learner not found or failed to load: {error}</p>
        <Button variant="secondary" onClick={goBack}>
          {backLabel}
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl pb-10">
      {/* ── Back Navigation ── */}
      <button 
        className="mb-5 text-sm font-medium text-brand-fg-muted hover:text-brand-fg transition-colors"
        onClick={goBack}
      >
        {backLabel}
      </button>

      {/* ── Header ── */}
      <div className="mb-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 rounded-2xl bg-white p-6 shadow-sm border border-brand-border">
        <div className="flex items-center gap-5">
          {/* Avatar */}
          <div 
            className="flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-full border-[3px] bg-brand-muted text-[28px] font-bold"
            style={{ borderColor: student.color, color: student.color }}
          >
            {student.initial}
          </div>
          {/* Name & Badges */}
          <div>
            <h1 className="text-[22px] font-bold text-brand-fg">{student.name}</h1>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">{student.band}</span>
              <span className="rounded bg-gray-100 px-2 py-0.5 text-xs font-semibold text-gray-700">{student.tier}</span>
              {isCaseload && (
                <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                  Caseload
                </span>
              )}
            </div>
          </div>
        </div>

        {/* ── Actions — for EVERY learner ──
            Not gated on the caseload any more. A profile is now just the learner's DIAL marks,
            and the research cohort has those, so there is nothing here they cannot do. Generate
            Profile promotes their most recent sitting; if they have no scores at all it opens
            the upload flow rather than erroring. */}
        {/* Column sizes to its widest child — the button row — and `items-stretch` (the flex
            default) then makes the focus input below exactly that wide. */}
        <div className="flex flex-col gap-2.5">
          <div className="flex flex-wrap gap-2.5">
            <Button variant="primary" onClick={handleGenerateProfile} disabled={isGenerating}>
              {isGenerating ? "Generating..." : "Generate Profile"}
            </Button>
            <Button
              variant="secondary"
              onClick={handleGenerateActivity}
              loading={isGeneratingActivity}
            >
              Generate Activity
            </Button>
            <Button variant="secondary" onClick={() => setIsSharing(true)} disabled={!latestActivity}>Share</Button>
          </div>

          {/* Optional steer, appended to the query built from the learner's marks. Left blank,
              the activity targets whichever skills they score lowest on.
              `min-w-0` stops the input's own intrinsic width from widening the column past the
              buttons — it should follow their width, never set it. */}
          <input
            type="text"
            aria-label="Optional focus"
            placeholder="Optional focus, e.g. rhyming games, short vowels…"
            className="h-11 w-full min-w-0 rounded-lg border-2 border-brand-border px-4 text-sm outline-none transition-colors focus:border-brand-primary"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
      </div>

      {/* ── Generation failed, in one of two different ways ──
          A thrown error means the request never completed. A refusal means it did, and the
          answer was no. Both leave any previously generated activity below untouched. */}
      {activityResult?.error && (
        <div className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">
          <p className="font-medium">Could not generate activity</p>
          <p className="mt-1 text-sm">{activityResult.error}</p>
        </div>
      )}

      {refused && (
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900">
          <p className="font-medium">
            {noScores ? "This learner has no assessment scores yet" : "Not enough curriculum grounding"}
          </p>
          <p className="mt-1 text-sm">
            {noScores
              ? "The activity is built from their DIAL marks, and there are none on record. Upload an assessment for them first."
              : activityResult.reason}
          </p>
          {activityResult.query && (
            <p className="mt-2 text-xs opacity-80">Query: “{activityResult.query}”</p>
          )}
        </div>
      )}

      {/* ── Deficiency Alerts — the DIAL marks this learner is furthest behind on ── */}
      {hasScores && (
        <>
          <h2 className="mb-3 text-[15px] font-semibold text-brand-fg">Skill Deficiency Alerts</h2>
          <DeficiencyAlerts metrics={metrics} />
        </>
      )}

      {/* ── Skills Visualisation ──
          Two views of the SAME four marks, answering different questions:
            DIAL Assessment     where the learner stands NOW, across all four at once
            Progress & Activity how ONE mark has moved across every semester on record
          Both are empty for a learner with no scores, and both say so — that is the cue to
          upload an assessment, which the right-hand card offers directly. */}
      <h2 className="mb-3 text-[15px] font-semibold text-brand-fg">Skills Overview</h2>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="rounded-xl border border-brand-border bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-sm font-semibold text-brand-fg">DIAL Assessment</h3>
          <p className="mb-4 text-xs text-brand-fg-muted">
            {overview?.semester
              ? `${overview.semester}${overview.band ? ` · Band ${overview.band}` : ""}`
              : "Marks from the DAS assessment papers"}
          </p>
          {overview?.metrics?.length ? (
            <ProfileRadarChart metrics={overview.metrics} band={overview.band_group} />
          ) : (
            <div className="rounded-lg border border-dashed border-brand-border bg-brand-muted p-6 text-center">
              <p className="text-sm text-brand-fg">No DIAL marks</p>
              <p className="mt-2 text-xs text-brand-fg-muted">
                This learner has no scores from the DAS assessment papers — they were added in
                the app rather than loaded from the workbook.
              </p>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-brand-border bg-white p-5 shadow-sm">
          <h3 className="mb-1 text-sm font-semibold text-brand-fg">Progress & Activity</h3>
          <p className="mb-4 text-xs text-brand-fg-muted">
            {history.length > 1
              ? `${history.length} sittings, ${history[0].semester} to ${history[history.length - 1].semester}`
              : "Scores across every semester on record"}
          </p>
          {history.length > 0 ? (
            <ScoreHistoryChart history={history} />
          ) : (
            <div className="rounded-lg border border-dashed border-brand-border bg-brand-muted p-6 text-center">
              <p className="text-sm text-brand-fg">No assessment scores yet</p>
              <p className="mt-2 text-xs text-brand-fg-muted">
                Nothing has been recorded for this learner. Upload an assessment to give them a
                starting point.
              </p>
              <Button
                variant="secondary"
                className="mt-4"
                onClick={() => setIsUploading(true)}
              >
                Upload assessment data
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Last activity and its reviews. Shown whenever one exists — any learner can have an
          activity generated for them now, so there is nothing to gate on. */}
      {latestActivity && (
        <>
          <h2 className="mb-3 mt-8 text-[15px] font-semibold text-brand-fg">Activity & Review</h2>
          <div className="space-y-4">
            <ActivityReviewPanel activity={latestActivity} />
            {/* Read off the STORED row, not the generation response, so it is there for anyone
                who opens this learner later — including a therapist who never ran it. */}
            <GroundingSources
              grounding={latestActivity.content?.grounding}
              groundedOn={latestActivity.grounded_on}
              query={latestActivity.content?.query}
            />
            <ReviewSection
              activityId={latestActivity.id}
            />
          </div>
        </>
      )}

      {/* UC1's upload flow, opened on this learner. It takes a list and pre-selects the first,
          so handing it one entry is how the picker is skipped. Reloads on save so the chart
          picks up the new sitting without a page refresh. */}
      {isUploading && (
        <UploadView
          learners={[{ ...student, id }]}
          onClose={() => setIsUploading(false)}
          onSaved={() => {
            setIsUploading(false);
            loadData();
          }}
        />
      )}

      {isSharing && latestActivity && (
        <ShareWindow activityId={latestActivity.id} activityName={latestActivity.literacy_objective
            ? `"${latestActivity.literacy_objective}"`
            : `the latest activity for ${student.name}`}
          onClose={() => setIsSharing(false)}
        />
      )}
    </div>
  );
}
