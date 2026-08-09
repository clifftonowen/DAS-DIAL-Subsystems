// LearnersPage.jsx — a searchable, paged grid of learners.
// Rendered at route "/learners" inside the Dashboard shell. Clicking a card opens /learners/:id.
//
// PAGED AND SEARCHED SERVER-SIDE, which is the whole shape of this file. `learners` holds the
// ~5,783-row anonymised DAS research cohort alongside the therapist's ten, so the old approach —
// fetch every learner, filter with Array.filter, render one card each — breaks twice over:
// PostgREST caps a select at 1,000 rows and truncates WITHOUT erroring, and 5,783 cards is a
// visible freeze on every keystroke.
//
// The caseload toggle defaults ON. This tab is where a therapist works with their own learners;
// opening it on thousands of anonymised research rows would bury them. The cohort is one click
// away, and the dashboard's scatter shows it whole anyway.

import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import StudentCard from "../components/StudentCard";
import Button from "../components/Button";
import UploadView from "./UploadView";
import { listLearners } from "../lib/api";

const PER_PAGE = 24;

// Long enough that typing a name is one request rather than one per letter, short enough that
// the grid still feels live.
const SEARCH_DEBOUNCE_MS = 300;

// A cohort learner has no pseudonym — their anonymised workbook id is the only name they have.
const displayName = (l) => l.pseudonym || l.student_id || "Unknown";

// 'A2' where the fine band is known; otherwise the band group, which is all the source recorded.
const displayBand = (l) => l.band || (l.band_group ? `Band ${l.band_group}` : "—");

export default function LearnersPage() {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");
  // Separate from searchQuery so the input stays responsive while the request is debounced.
  const [activeQuery, setActiveQuery] = useState("");
  const [caseloadOnly, setCaseloadOnly] = useState(true);
  const [page, setPage] = useState(1);

  const [learners, setLearners] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showUpload, setShowUpload] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setActiveQuery(searchQuery);
      setPage(1);   // a new search starts at the beginning, or page 7 of the old results 404s
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const loadLearners = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listLearners({
        page,
        perPage: PER_PAGE,
        q: activeQuery,
        caseload: caseloadOnly,
      });
      setLearners(
        (data.items || []).map((l) => ({
          ...l,
          name: displayName(l),
          band: displayBand(l),
          tier: l.tier || (l.on_caseload ? "Tier 2" : "DAS cohort"),
          initial: displayName(l).charAt(0).toUpperCase(),
          // Derived from the id rather than random, so a card keeps its colour across pages and
          // re-renders. Math.random() here used to reshuffle the whole grid on every fetch.
          color: CARD_COLORS[hashCode(l.id) % CARD_COLORS.length],
        }))
      );
      setTotal(data.total || 0);
    } catch (err) {
      console.error("Failed to fetch learners", err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [page, activeQuery, caseloadOnly]);

  useEffect(() => {
    loadLearners();
  }, [loadLearners]);

  const lastPage = Math.max(1, Math.ceil(total / PER_PAGE));
  const firstShown = total === 0 ? 0 : (page - 1) * PER_PAGE + 1;
  const lastShown = Math.min(page * PER_PAGE, total);

  return (
    <div className="flex h-full flex-col">
      {/* ── Top Bar ── */}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-2 rounded-lg border border-brand-border bg-white px-3 py-2 text-sm text-brand-fg focus-within:border-brand-primary focus-within:ring-1 focus-within:ring-brand-primary">
            <input
              type="text"
              placeholder="Search name, student id or band…"
              aria-label="Search learners"
              className="border-none bg-transparent outline-none min-w-[220px]"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Caseload toggle — aria-pressed rather than a checkbox so it matches the chip
              controls on the dashboard scatter. */}
          <button
            type="button"
            aria-pressed={caseloadOnly}
            onClick={() => {
              setCaseloadOnly((on) => !on);
              setPage(1);
            }}
            className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
              caseloadOnly
                ? "border-brand-primary bg-brand-muted text-brand-fg"
                : "border-brand-border bg-white text-brand-fg-muted hover:bg-brand-muted"
            }`}
          >
            My caseload only
          </button>
        </div>

        <Button onClick={() => setShowUpload(true)}>Upload Assessment</Button>
      </div>

      {/* ── Result count ── */}
      {!loading && !error && (
        <p className="mb-3 text-xs text-brand-fg-muted">
          {total === 0
            ? "No learners found."
            : `Showing ${firstShown.toLocaleString()}–${lastShown.toLocaleString()} of ${total.toLocaleString()}`}
          {!caseloadOnly && total > 0 && " · includes the anonymised DAS research cohort"}
        </p>
      )}

      {/* ── States & Grid ── */}
      {loading ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-[14px]">
          {Array.from({ length: 6 }, (_, i) => (
            <div
              key={i}
              className="h-40 rounded-xl bg-gray-100 animate-pulse border border-brand-border"
            />
          ))}
        </div>
      ) : error ? (
        <div className="py-10 text-center text-red-600">Failed to load learners: {error}</div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-[14px] overflow-y-auto pb-5">
          {learners.map((student) => (
            <StudentCard
              key={student.id}
              student={student}
              onClick={() => navigate(`/learners/${student.id}`)}
            />
          ))}
          {learners.length === 0 && (
            <div className="col-span-full py-10 text-center text-sm text-brand-fg-muted">
              {activeQuery
                ? `No learners match “${activeQuery}”.`
                : caseloadOnly
                ? "No learners on your caseload yet."
                : "No learners found."}
            </div>
          )}
        </div>
      )}

      {/* ── Pager ── */}
      {!loading && !error && lastPage > 1 && (
        <nav aria-label="Pagination" className="mt-4 flex items-center justify-center gap-3">
          <PagerButton onClick={() => setPage((p) => p - 1)} disabled={page <= 1}>
            ← Previous
          </PagerButton>
          <span className="text-xs tabular-nums text-brand-fg-muted">
            Page {page.toLocaleString()} of {lastPage.toLocaleString()}
          </span>
          <PagerButton onClick={() => setPage((p) => p + 1)} disabled={page >= lastPage}>
            Next →
          </PagerButton>
        </nav>
      )}

      {showUpload && (
        <UploadView
          // Only caseload learners can receive an assessment — a cohort row has no therapist
          // behind it — so the picker never offers the rest.
          learners={learners.filter((l) => l.on_caseload)}
          onClose={() => setShowUpload(false)}
          onSaved={loadLearners}
        />
      )}
    </div>
  );
}

function PagerButton({ onClick, disabled, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-lg border border-brand-border bg-white px-3 py-1.5 text-xs font-semibold text-brand-fg transition-colors hover:bg-brand-muted disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

const CARD_COLORS = ["#FF2E45", "#FFCA28", "#2563EB", "#22A06B", "#7C3AED"];

// Stable per-id colour. Any cheap spread over the palette will do — this is decoration, not
// identity — but it must be deterministic, or cards change colour every time the page reloads.
function hashCode(value) {
  let hash = 0;
  for (const char of String(value)) {
    hash = (hash * 31 + char.charCodeAt(0)) | 0;
  }
  return Math.abs(hash);
}
