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

export const listLearners = () => api("/learners");
export const generateProfile = (learnerId) => api(`/profiles/${learnerId}`, { method: "POST" });
// Curriculum-grounded generation. `id` may be a profile id or a learner id — the
// backend resolves either against learner_profiles and derives the retrieval query
// from that profile. `params` only steers it: { band, concept, stage, notes, k }.
// Resolves to { status: "GENERATED" | "INSUFFICIENT_CONTEXT", content, query,
//               grounding: [{ title, source, page, concept, stage, similarity }],
//               profile_id, reason? }
export const generateActivity = (id, params = {}) =>
  api(`/activities/${id}/generate`, { method: "POST", body: JSON.stringify(params) });

// New GET endpoints added per implementation plan
export const getLearner = (learnerId) => api(`/learners/${learnerId}`);
export const getLearnerProfiles = (learnerId) => api(`/learners/${learnerId}/profiles`);
export const getLearnerAssessments = (learnerId) => api(`/learners/${learnerId}/assessments`);
export const getProfileActivities = (profileId) => api(`/profiles/${profileId}/activities`);

export const shareActivity = (activityId, recipientEmail) =>
  api("/share", { method: "POST", body: JSON.stringify({ activity_id : activityId, recipient_email:recipientEmail }) });
export const submitReview = (activityId, text) =>
  api("/reviews", { method: "POST", body: JSON.stringify({ activity_id: activityId, text }) });
export const getReviews = (activityId) => api(`/reviews/${activityId}`);


// Dashboard endpoints
export const getDashboardStats = () => api("/dashboard/stats");
export const getDashboardTasks = () => api("/dashboard/tasks");
export const getDashboardEvents = () => api("/dashboard/events");


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