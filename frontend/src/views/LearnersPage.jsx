// LearnersPage.jsx — Displays a searchable grid of all learners.
// Rendered at route "/learners" inside the Dashboard shell.
//
// Matches the prototype's learners list view. Clicking a card navigates
// to /learners/:id. The data is currently hardcoded for the prototype.

import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import StudentCard from "../components/StudentCard";
import Button from "../components/Button";
import UploadView from "./UploadView";
import { listLearners } from "../lib/api";

export default function LearnersPage() {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");
  const [learners, setLearners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // Controls whether the Upload Assessment modal is shown over the page.
  const [showUpload, setShowUpload] = useState(false);

  async function loadLearners() {
    try {
      const data = await listLearners();
      // The API returns an array of learners, but we need to ensure they have
      // fallback properties for UI rendering (like color, initial, name).
      // If the DB has `pseudonym` instead of `name` (per schema), map it:
      const formatted = data.map(l => ({
        ...l,
        name: l.pseudonym || l.name,
        band: l.band_level || l.band,
        tier: l.tier || "Tier 2",
        initial: (l.pseudonym || l.name || "?").charAt(0).toUpperCase(),
        // Pick a random brand color if none exists (just for prototype flair)
        color: ['#FF2E45', '#FFCA28', '#2563EB', '#22A06B', '#7C3AED'][Math.floor(Math.random() * 5)]
      }));
      setLearners(formatted);
    } catch (err) {
      console.error("Failed to fetch learners", err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLearners();
  }, []);

  // Filter learners based on search query (by name or band)
  const filteredStudents = learners.filter(
    (s) =>
      (s.name || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      (s.band || "").toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex h-full flex-col">
      {/* ── Top Bar ── */}
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          {/* Search bar */}
          <div className="flex items-center gap-2 rounded-lg border border-brand-border bg-white px-3 py-2 text-sm text-brand-fg focus-within:border-brand-primary focus-within:ring-1 focus-within:ring-brand-primary">
            <input
              type="text"
              placeholder="Search learners…"
              className="border-none bg-transparent outline-none min-w-[200px]"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          
          {/* Filter button */}
          <button className="flex items-center gap-1.5 rounded-lg border border-brand-border bg-white px-3 py-2 text-sm font-medium text-brand-fg transition-colors hover:bg-brand-muted">
            Filter
          </button>
        </div>

        <Button onClick={() => setShowUpload(true)}>
          Upload Assessment
        </Button>
      </div>

      {/* ── States & Grid ── */}
      {loading ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-[14px]">
          {/* Loading Skeletons */}
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="h-40 rounded-xl bg-gray-100 animate-pulse border border-brand-border" />
          ))}
        </div>
      ) : error ? (
        <div className="py-10 text-center text-red-600">Failed to load learners: {error}</div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-[14px] overflow-y-auto pb-5">
          {filteredStudents.map((student) => (
            <StudentCard
              key={student.id}
              student={student}
              onClick={() => navigate(`/learners/${student.id}`)}
            />
          ))}
          {filteredStudents.length === 0 && (
            <div className="col-span-full py-10 text-center text-sm text-brand-fg-muted">
              No learners found.
            </div>
          )}
        </div>
      )}

      {/* ── Upload Assessment modal ── */}
      {showUpload && (
        <UploadView
          learners={learners}
          onClose={() => setShowUpload(false)}
          onSaved={loadLearners}
        />
      )}
    </div>
  );
}
