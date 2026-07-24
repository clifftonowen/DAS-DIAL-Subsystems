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
export const generateActivity = (profileId, params) =>
  api(`/activities/${profileId}/generate`, { method: "POST", body: JSON.stringify(params) });

// New GET endpoints added per implementation plan
export const getLearner = (learnerId) => api(`/learners/${learnerId}`);
export const getLearnerProfiles = (learnerId) => api(`/learners/${learnerId}/profiles`);
export const getLearnerAssessments = (learnerId) => api(`/learners/${learnerId}/assessments`);
export const getProfileActivities = (profileId) => api(`/profiles/${profileId}/activities`);

// Dashboard endpoints
export const getDashboardStats = () => api("/dashboard/stats");
export const getDashboardTasks = () => api("/dashboard/tasks");
export const getDashboardEvents = () => api("/dashboard/events");

