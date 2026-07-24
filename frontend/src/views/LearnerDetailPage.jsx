// LearnerDetailPage.jsx — Detailed view for a specific learner.
// Rendered at route "/learners/:id" inside the Dashboard shell.
//
// Displays the learner's profile header, deficiency alerts, radar chart,
// and skill progress bars. Data is hardcoded for the prototype.

import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Button from "../components/Button";
import DeficiencyAlerts from "../components/DeficiencyAlerts";
import ProfileRadarChart from "../components/ProfileRadarChart";
import SkillBars from "../components/SkillBars";
import { getLearner, getLearnerProfiles, generateProfile } from "../lib/api";

export default function LearnerDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  
  const [student, setStudent] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);

  async function loadData() {
    setLoading(true);
    try {
      const learnerData = await getLearner(id);
      
      const formattedLearner = {
        ...learnerData,
        name: learnerData.pseudonym || learnerData.name,
        band: learnerData.band_level || learnerData.band,
        tier: learnerData.tier || "Tier 2",
        initial: (learnerData.pseudonym || learnerData.name || "?").charAt(0).toUpperCase(),
        color: ['#E91626', '#F8B508', '#2563EB', '#15803D', '#7C3AED'][Math.floor(Math.random() * 5)]
      };
      setStudent(formattedLearner);

      // Fetch profiles
      const profilesData = await getLearnerProfiles(id);
      if (profilesData && profilesData.length > 0) {
        // Assume sorted by most recent
        const latestProfile = profilesData[0];
        setProfile({
          phonological: (latestProfile.phonological_processing || 0) * 100,
          decoding: (latestProfile.decoding || 0) * 100,
          spelling: (latestProfile.spelling || 0) * 100,
          comprehension: (latestProfile.comprehension || 0) * 100,
          workingMemory: (latestProfile.working_memory || 0) * 100,
          executive: (latestProfile.executive_functioning || 0) * 100,
          visualisation: (latestProfile.visualisation || 0) * 100,
        });
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

  const handleGenerateProfile = async () => {
    setIsGenerating(true);
    try {
      await generateProfile(id);
      await loadData(); // Reload to get the new profile
    } catch (err) {
      alert("Failed to generate profile: " + err.message);
    } finally {
      setIsGenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-brand-border border-t-brand-primary"></div>
      </div>
    );
  }

  if (error || !student) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-brand-fg-muted">Learner not found or failed to load: {error}</p>
        <Button variant="secondary" onClick={() => navigate("/learners")}>
          ← Back to Learners
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl pb-10">
      {/* ── Back Navigation ── */}
      <button 
        className="mb-5 text-sm font-medium text-brand-fg-muted hover:text-brand-fg transition-colors"
        onClick={() => navigate("/learners")}
      >
        ← Back to Learners
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
              <span className="rounded bg-green-50 px-2 py-0.5 text-xs font-semibold text-green-700">
                Data loaded from API
              </span>
            </div>
          </div>
        </div>
        
        {/* Actions */}
        <div className="flex flex-wrap gap-2.5">
          <Button variant="primary" onClick={handleGenerateProfile} disabled={isGenerating}>
            {isGenerating ? "Generating..." : "Generate Profile"}
          </Button>
          <Button variant="secondary" onClick={() => navigate("/generate")}>Generate Activity</Button>
          <Button variant="ghost">Share</Button>
        </div>
      </div>

      {profile ? (
        <>
          {/* ── Deficiency Alerts ── */}
          <h2 className="mb-3 text-[15px] font-semibold text-brand-fg">Skill Deficiency Alerts</h2>
          <DeficiencyAlerts skills={profile} />

          {/* ── Skills Visualisation ── */}
          <h2 className="mb-3 text-[15px] font-semibold text-brand-fg">Skills Overview</h2>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {/* Radar Chart */}
            <div className="rounded-xl border border-brand-border bg-white p-5 shadow-sm">
              <h3 className="mb-4 text-sm font-semibold text-brand-fg">Cognitive Profile</h3>
              <ProfileRadarChart skills={profile} />
            </div>

            {/* Skill Bars */}
            <div className="rounded-xl border border-brand-border bg-white p-5 shadow-sm">
              <h3 className="mb-4 text-sm font-semibold text-brand-fg">Progress & Activity</h3>
              <SkillBars skills={profile} />
            </div>
          </div>
        </>
      ) : (
        <div className="rounded-xl border border-dashed border-brand-border bg-brand-muted p-10 text-center">
          <h3 className="text-lg font-medium text-brand-fg">No cognitive profile yet</h3>
          <p className="mt-2 text-sm text-brand-fg-muted">Click "Generate Profile" to run the profiling algorithm against this learner's assessment history.</p>
        </div>
      )}
    </div>
  );
}
