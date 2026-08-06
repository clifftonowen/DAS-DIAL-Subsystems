// GeneratePage.jsx — Interface for generating learning activities.
// Rendered at route "/generate" inside the Dashboard shell.
//
// Search a learner, then generate. The learner's DIAL marks are the input: the backend builds
// the retrieval query from the two they rank LOWEST on by percentile, grounds the activity in
// curriculum_chunks, and refuses (INSUFFICIENT_CONTEXT) rather than inventing one when the
// corpus does not cover the need. The optional notes field only steers that query.
//
// SEARCH RUNS SERVER-SIDE. `learners` holds the ~5,783-row anonymised research cohort as well
// as the therapist's own, and PostgREST truncates an unpaged select at 1,000 rows without
// erroring — so fetching everything and filtering in the browser would search a fraction of
// the table and look like it was working.

import { useState, useRef, useEffect, useCallback } from "react";
import Button from "../components/Button";
import ActivityContent from "../components/ActivityContent";
import { listLearners, generateActivity } from "../lib/api";

export default function GeneratePage() {
  const [query, setQuery] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [learners, setLearners] = useState([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [notes, setNotes] = useState("");
  const [result, setResult] = useState(null);   // API payload, or { error } on failure

  const dropdownRef = useRef(null);

  // One request per settled query, not per keystroke, and never for an empty box — the
  // dropdown only opens once you have typed something.
  useEffect(() => {
    const text = query.trim();
    if (!text || selectedStudent?.name === text) {
      setLearners([]);
      return undefined;
    }
    const timer = setTimeout(async () => {
      try {
        // caseload:false so the research cohort is searchable too — every learner has marks,
        // so every learner can have an activity generated for them.
        const data = await listLearners({ q: text, perPage: 20, caseload: false });
        setLearners(
          (data.items || []).map((l) => ({
            ...l,
            // A cohort learner is anonymised; their workbook id is the only name they have.
            name: l.pseudonym || l.student_id || "Unknown",
            band: l.band || (l.band_group ? `Band ${l.band_group}` : "—"),
            tier: l.tier || (l.on_caseload ? "Tier 2" : "DAS cohort"),
            initial: (l.pseudonym || l.student_id || "?").charAt(0).toUpperCase(),
          }))
        );
      } catch (err) {
        console.error("Failed to search learners", err);
        setLearners([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [query, selectedStudent]);

  // The server already filtered; this is just what came back.
  const matches = learners;

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
      // The learner id is enough — the backend reads their four DIAL marks and builds the
      // query from the two they rank lowest on. Band is passed only when it matches the
      // curriculum's own vocabulary; any other value would filter the corpus to
      // nothing and turn every request into a refusal.
      const band = /^A[123]$/.test(selectedStudent.band || "") ? selectedStudent.band : undefined;
      const data = await generateActivity(selectedStudent.id, { band, notes: notes.trim() });
      setResult(data);
    } catch (err) {
      console.error(err);
      setResult({ error: err.message });
    } finally {
      setIsGenerating(false);
    }
  };

  // Refusals come back 200 with a status, not as thrown errors — the request
  // succeeded, the corpus just did not cover this learner's need.
  const refused = result?.status === "INSUFFICIENT_CONTEXT";
  // An EMPTY QUERY is the signal that the learner has no marks to steer with — build_query
  // returns "" when no metric has a percentile and the therapist left the notes blank, and the
  // similarity gate then refuses rather than letting the LLM invent from nothing. Checking the
  // query rather than an id: every request carries a learner id now, so that told us nothing.
  const noScores = refused && !result.query;

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

      {/* ── Optional steer — appended to the profile-derived retrieval query ── */}
      <input
        type="text"
        placeholder="Optional focus, e.g. rhyming games, short vowels…"
        className="mt-3 h-11 w-full rounded-lg border-2 border-brand-border px-4 text-sm outline-none transition-colors focus:border-brand-primary"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />

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

      {/* ── Request failed (network / 4xx / 5xx) ── */}
      {result?.error && (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">
          <p className="font-medium">Could not generate activity</p>
          <p className="mt-1 text-sm">{result.error}</p>
        </div>
      )}

      {/* ── Refused: the curriculum does not cover this learner's need ── */}
      {refused && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900">
          <p className="font-medium">
            {noScores ? "This learner has no assessment scores yet" : "Not enough curriculum grounding"}
          </p>
          <p className="mt-1 text-sm">
            {noScores
              ? "The activity is built from their DIAL marks, and there are none on record. Upload an assessment for them first."
              : result.reason}
          </p>
          {result.query && (
            <p className="mt-2 text-xs opacity-80">Query: “{result.query}”</p>
          )}
        </div>
      )}

      {/* ── Generated activity + the curriculum it was grounded in ── */}
      {result?.status === "GENERATED" && (
        <div className="mt-4 space-y-4">
          <div className="overflow-hidden rounded-xl border border-brand-border bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-brand-border bg-brand-muted/50 px-6 py-3">
              <p className="text-sm font-semibold text-brand-fg">Generated activity</p>
              <span className="rounded bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-700">
                Grounded in {result.grounding?.length ?? 0} source
                {result.grounding?.length === 1 ? "" : "s"}
              </span>
            </div>
            {/* ActivityContent parses the model's Markdown — no raw ** on screen */}
            <div className="px-6 py-5">
              <ActivityContent text={result.content} />
            </div>
          </div>

          {result.grounding?.length > 0 && (
            <div className="rounded-xl border border-brand-border bg-white p-5 shadow-sm">
              <p className="mb-3 text-sm font-semibold text-brand-fg">Grounding sources</p>
              <ul className="space-y-2.5">
                {result.grounding.map((g, i) => (
                  <li key={i} className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-brand-fg">{g.title}</p>
                      <p className="text-[11px] text-brand-fg-muted">
                        {[g.source && `${g.source} p.${g.page ?? "?"}`, g.concept, g.stage]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </div>
                    {typeof g.similarity === "number" && (
                      <span className="shrink-0 rounded bg-brand-muted px-2 py-0.5 text-[11px] font-medium text-brand-fg-muted">
                        {g.similarity.toFixed(2)}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-[11px] text-brand-fg-muted">Query: “{result.query}”</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
