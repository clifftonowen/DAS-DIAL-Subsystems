// GeneratePage.jsx — Interface for generating learning activities.
// Rendered at route "/generate" inside the Dashboard shell.
//
// Allows searching for a learner with an autocomplete dropdown,
// selecting them, and (eventually) triggering activity generation.

import { useState, useRef, useEffect } from "react";
import Button from "../components/Button";
import { listLearners, generateActivity } from "../lib/api";

export default function GeneratePage() {
  const [query, setQuery] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [learners, setLearners] = useState([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState(null);
  
  const dropdownRef = useRef(null);

  useEffect(() => {
    async function loadLearners() {
      try {
        const data = await listLearners();
        const formatted = data.map(l => ({
          ...l,
          name: l.pseudonym || l.name,
          band: l.band_level || l.band,
          tier: l.tier || "Tier 2",
          initial: (l.pseudonym || l.name || "?").charAt(0).toUpperCase(),
          color: ['#FF2E45', '#FFCA28', '#2563EB', '#22A06B', '#7C3AED'][Math.floor(Math.random() * 5)]
        }));
        setLearners(formatted);
      } catch (err) {
        console.error("Failed to load learners for generation page", err);
      }
    }
    loadLearners();
  }, []);

  // Filter students based on search query
  const matches = query.trim()
    ? learners.filter((s) => (s.name || "").toLowerCase().includes(query.toLowerCase()))
    : [];

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (student) => {
    setSelectedStudent(student);
    setQuery(student.name);
    setIsDropdownOpen(false);
    setResult(null); // Clear previous results when selecting new student
  };

  const handleSearchChange = (e) => {
    setQuery(e.target.value);
    setIsDropdownOpen(true);
    if (selectedStudent && e.target.value !== selectedStudent.name) {
      // Clear selection if they start typing something else
      setSelectedStudent(null);
      setResult(null);
    }
  };

  const handleGenerate = async () => {
    if (!selectedStudent) return;
    setIsGenerating(true);
    setResult(null);
    try {
      // Assuming we just pass the learner's ID as the profile_id to keep it simple, 
      // or we'd ideally fetch their most recent profile ID. For now:
      const activity = await generateActivity(selectedStudent.id, { theme: "General" });
      setResult({ success: true, message: "Activity generated successfully!", data: activity });
    } catch (err) {
      console.error(err);
      setResult({ success: false, message: "Failed to generate activity: " + err.message });
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="mx-auto mt-10 w-full max-w-2xl">
      <h1 className="mb-2 text-2xl font-bold text-brand-fg">Generate Learning Activity</h1>
      <p className="mb-8 text-brand-fg-muted">
        Search for a learner to create a personalised activity based on their profile
      </p>

      {/* ── Search Bar & Generate Button ── */}
      <div className="flex items-stretch gap-3">
        <div className="relative flex-1" ref={dropdownRef}>
          {/* Search Input */}
          <div className="relative">
            <input
              type="text"
              placeholder="Type a learner's name…"
              className="h-12 w-full rounded-lg border-2 border-brand-border py-0 pl-4 pr-4 text-base outline-none transition-colors focus:border-brand-primary"
              value={query}
              onChange={handleSearchChange}
              onFocus={() => setIsDropdownOpen(true)}
              autoComplete="off"
            />
          </div>

          {/* Autocomplete Dropdown */}
          {isDropdownOpen && query.trim().length > 0 && (
            <div className="absolute left-0 right-0 top-full z-20 mt-2 max-h-[300px] overflow-y-auto rounded-lg border border-brand-border bg-white shadow-lg">
              {matches.length === 0 ? (
                <div className="p-4 text-sm text-brand-fg-muted">No learners found</div>
              ) : (
                matches.map((student, index) => (
                  <div key={student.id}>
                    {index > 0 && <div className="h-px bg-brand-border mx-2" />}
                    <div
                      className="flex cursor-pointer items-center gap-3 p-3 transition-colors hover:bg-brand-muted"
                      onClick={() => handleSelect(student)}
                    >
                      <div
                        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 bg-brand-muted text-base font-semibold"
                        style={{ color: student.color, borderColor: student.color }}
                      >
                        {student.initial}
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-brand-fg">{student.name}</div>
                        <div className="text-xs text-brand-fg-muted">
                          {student.band} · {student.tier}
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Generate Button */}
        <Button 
          variant="primary" 
          disabled={!selectedStudent || isGenerating}
          onClick={handleGenerate}
          className="h-12 px-6"
        >
          {isGenerating ? "Generating..." : "Generate"}
        </Button>
      </div>

      {/* ── Selected Learner Card ── */}
      {selectedStudent && (
        <div className="mt-6 flex items-center gap-4 rounded-xl border border-brand-border bg-white p-4 shadow-sm animate-in fade-in slide-in-from-top-2">
          <div
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border-2 bg-brand-muted text-xl font-semibold"
            style={{ color: selectedStudent.color, borderColor: selectedStudent.color }}
          >
            {selectedStudent.initial}
          </div>
          <div className="flex-1">
            <div className="text-[15px] font-semibold text-brand-fg">{selectedStudent.name}</div>
            <div className="text-[13px] text-brand-fg-muted">
              {selectedStudent.band} · {selectedStudent.tier}
            </div>
          </div>
          <span className="rounded bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-700">
            Ready to generate
          </span>
        </div>
      )}

      {/* ── Generation Result ── */}
      {result && (
        <div className={`mt-4 rounded-xl p-4 border ${result.success ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-800'}`}>
          <p className="font-medium">{result.message}</p>
        </div>
      )}
    </div>
  );
}
