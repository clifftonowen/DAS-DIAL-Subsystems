import { supabase } from "./supabase";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function authHeader() {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(await authHeader()), ...options.headers };
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  // Read the body before checking `ok` so FastAPI's `detail` survives into the
  // thrown Error — the UI has no other way to show why a request failed. The
  // catch covers empty bodies (e.g. 204 from /auth/logout).
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorMessage(res, data));
  return data;
}

/** FastAPI sends `detail` as a string for HTTPException but as a list of
 *  {loc, msg, type} objects for 422 validation errors. Stringifying the list
 *  would put "[object Object]" in front of the user, so pull out the first msg. */
function errorMessage(res, data) {
  const { detail } = data;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return `${res.status} ${res.statusText}`;
}

// Auth — the AuthView -> AuthController messages in the UC6 and UC8 sequence
// diagrams. These are the only calls made before a session exists, so
// authHeader() contributes nothing to them.
export const logIn = (email, password) =>
  api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const signUp = (email, password) =>
  api("/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) });

// One PAGE of learners, not all of them. `learners` holds the ~5,783-row anonymised DAS cohort
// alongside the therapist's caseload, so the list is paged and searched server-side.
// Resolves to { items: [{ id, student_id, pseudonym, tier, on_caseload, band, band_group,
//                         cluster_cohort }], total, page, per_page }
// `total` counts everything matching the CURRENT filters, so the pager reads correctly for a
// search as well as for the unfiltered list. `caseload` defaults true — the Learners tab opens
// on the therapist's own learners rather than on thousands of research rows.
export const listLearners = ({ page = 1, perPage = 24, q = "", caseload = true } = {}) => {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
    caseload: String(caseload),
  });
  if (q) params.set("q", q);
  return api(`/learners?${params}`);
};
export const generateProfile = (learnerId) => api(`/profiles/${learnerId}`, { method: "POST" });
// Curriculum-grounded generation. Takes a LEARNER id: the backend reads their four DIAL marks
// and builds the retrieval query from the two they rank lowest on. `params` only steers it:
// { band, concept, stage, notes, k }.
// Resolves to { status: "GENERATED" | "INSUFFICIENT_CONTEXT", content, query,
//               grounding: [{ title, source, page, concept, stage, similarity }],
//               learner_id, reason? }
export const generateActivity = (learnerId, params = {}) =>
  api(`/activities/${learnerId}/generate`, { method: "POST", body: JSON.stringify(params) });

// New GET endpoints added per implementation plan
export const getLearner = (learnerId) => api(`/learners/${learnerId}`);
// Every sitting on record, oldest first. The profile page gets this inside
// getLearnerOverview; this is for callers that want the history alone.
export const getLearnerSittings = (learnerId) => api(`/learners/${learnerId}/sittings`);
export const getLearnerAssessments = (learnerId) => api(`/learners/${learnerId}/assessments`);
// Everything the profile page needs, in one call: the learner's CURRENT marks (the radar chart
// and the deficiency alerts) plus every sitting on record (the progress line chart). Resolves to
//   { learner_id, pseudonym, tier, on_caseload,
//     metrics: [{ key, label, raw, max, percentile, assessed }],
//     history: [{ semester, band, phonics, ..., phonics_pct, ... }],   // oldest first
//     student_id, semester, band, band_group, cluster_band, cluster_cohort }
// `metrics` all-unassessed and an empty `history` are ordinary states — a learner added in the
// app has no scores until an assessment is uploaded for them.
export const getLearnerOverview = (learnerId) => api(`/learners/${learnerId}/overview`);
// Activities generated for a learner, newest first. Keyed on the learner since
// `learning_activities.profiled` became `learner_id` — there is no profile row to hang
// them off now that a profile is just the learner's DIAL marks.
export const getLearnerActivities = (learnerId) => api(`/profiles/${learnerId}/activities`);


export const shareActivity = (activityId, recipientEmail) =>
  api("/share", { method: "POST", body: JSON.stringify({ activity_id : activityId, recipient_email:recipientEmail }) });
export const submitReview = (activityId, text, status = null) =>
  api("/reviews", { method: "POST", body: JSON.stringify({ activity_id: activityId, text, status }) });
export const getReviews = (activityId) => api(`/reviews/${activityId}`);



// Dashboard endpoints
export const getDashboardStats = () => api("/dashboard/stats");
export const getDashboardTasks = () => api("/dashboard/tasks");
export const getDashboardEvents = () => api("/dashboard/events");

// The whole clustered cohort in one call — every learner's literacy scores plus the k-means
// label already assigned to them, and one `runs` entry per band model describing how its k was
// chosen. Resolves to { learners: [...], runs: [...], unclustered: n }. See Graph.jsx.
export const getCohortClusters = () => api("/dashboard/clusters");


async function apiForm(path, formData) {
  const headers = await authHeader();
  const res = await fetch(`${BASE}${path}`, { method: "POST", headers, body: formData });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `${res.status} ${res.statusText}`);
  return data;
}

export function previewAssessment(learnerId, file) {
  const form = new FormData();
  form.append("learner_id", learnerId);
  form.append("file", file);
  return apiForm("/assessments/preview", form);
}

export const confirmAssessment = (payload) =>
  api("/assessments/confirm", { method: "POST", body: JSON.stringify(payload) });
