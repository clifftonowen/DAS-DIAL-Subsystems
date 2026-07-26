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
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

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