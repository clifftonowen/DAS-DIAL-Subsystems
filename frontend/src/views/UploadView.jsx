import { useEffect, useState } from "react";
import {
  previewAssessment, confirmAssessment, getAssessmentMetrics, getAssessmentSemesters,
} from "../lib/api";
import Card from "../components/Card";
import Button from "../components/Button";

const STEPS = { PICK: "pick", PREVIEW: "preview", DONE: "done" };

// Fallback only, for the moment before GET /assessments/metrics answers (and if it fails). The
// ceilings are SERVED — see the endpoint — so that the form and the confirm validator cannot
// disagree about what a valid mark is. Keeping a full copy here would recreate exactly that risk.
const METRIC_KEYS = [
  "writing_score", "phonics_score", "word_reading_score", "word_spelling_score",
];

// Band A never sits the writing paper, so "no mark" has to be expressible. The band a mark was
// earned against travels WITH the sitting because the rubric moves between bands.
const BAND_OPTIONS = ["A1", "A2", "A3", "B4", "B5", "B6", "C7", "C8", "C9"];
const bandGroupOf = (band) => (band ? band[0] : null);

export default function UploadView({ learners, onClose, onSaved }) {
  const [learnerId, setLearnerId] = useState(learners[0]?.id ?? "");
  const [file, setFile] = useState(null);
  const [step, setStep] = useState(STEPS.PICK);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [metricSpecs, setMetricSpecs] = useState([]);
  const [semesters, setSemesters] = useState([]);
  const [semester, setSemester] = useState("");
  const [band, setBand] = useState("");

  // EMPTY STRING, NOT "0". An untouched field means NOT ASSESSED, which is a different claim
  // from a mark of zero: writing is never administered to band A, and a 0 there would rank as
  // the learner's weakest skill and drive UC3 to generate a writing activity for a paper they
  // have never sat. Empty is sent as null and stored as null all the way down.
  const [metrics, setMetrics] = useState(() =>
    Object.fromEntries(METRIC_KEYS.map((key) => [key, ""]))
  );

  // The rubric and the semester list both come from the backend: the ceilings so the form agrees
  // with the validator, the semesters so the list cannot go stale when a new one begins.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [specs, options] = await Promise.all([
          getAssessmentMetrics(), getAssessmentSemesters(),
        ]);
        if (cancelled) return;
        setMetricSpecs(specs);
        setSemesters(options);
        setSemester((current) => current || options[0] || "");
      } catch {
        // Non-fatal: the form still works. The metric inputs fall back to unbounded entry and
        // the API rejects an out-of-range mark, which is the correct authority anyway.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Prefill the band from the learner being uploaded for, but leave it editable — a learner's
  // band changes between sittings, and this sitting records the paper they actually sat.
  useEffect(() => {
    const learner = learners.find((l) => l.id === learnerId);
    setBand(learner?.band ?? "");
  }, [learnerId, learners]);

  const specFor = (key) => metricSpecs.find((m) => m.key === key);

  function updateMetric(key, raw) {
    if (raw !== "" && !/^-?\d*\.?\d*$/.test(raw)) return;
    setMetrics((prev) => ({ ...prev, [key]: raw }));
  }

  function metricError(key) {
    const raw = metrics[key];
    if (raw === "") return null;              // not assessed — a valid answer, not an error
    if (raw === "-" || raw === ".") return "Enter a number";
    const n = Number(raw);
    if (isNaN(n)) return "Enter a number";
    const max = specFor(key)?.max;
    if (n < 0 || (max !== undefined && n > max)) return `Must be between 0 and ${max}`;
    return null;
  }

  const metricErrors = Object.fromEntries(METRIC_KEYS.map((key) => [key, metricError(key)]));
  const hasInvalidMetric = Object.values(metricErrors).some(Boolean);

  function toMetricNumbers() {
    // Blank -> null, NOT Number("") which is 0. This is the line that carries "not assessed"
    // across the wire; coercing here would silently assert a mark nobody entered.
    return Object.fromEntries(
      METRIC_KEYS.map((key) => [key, metrics[key] === "" ? null : Number(metrics[key])])
    );
  }

  async function handleParse(e) {
    e.preventDefault();
    if (!file || !learnerId || !semester || hasInvalidMetric) return;
    setLoading(true);
    setError("");
    try {
      const data = await previewAssessment(learnerId, file);
      setPreview(data);
      setStep(STEPS.PREVIEW);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm() {
    setLoading(true);
    setError("");
    try {
      await confirmAssessment({
        learner_id: preview.learner_id,
        assessment_date: preview.assessment_date,
        risk_score: preview.risk_score,
        task_results: preview.task_results,
        strengths: preview.strengths,
        weaknesses: preview.weaknesses,
        confidence_score: preview.confidence_score,
        // The sitting's identity: which semester these marks belong to, and which paper they
        // were earned against. Both are stored on learner_sittings, not just on the record.
        semester,
        band: band || null,
        band_group: bandGroupOf(band),
        ...toMetricNumbers(),
      });
      setStep(STEPS.DONE);
      onSaved?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <Card className="w-full max-w-lg space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-bold text-brand-fg">Upload Assessment Data</h2>
          <button onClick={onClose} className="text-brand-fg-muted hover:text-brand-fg">✕</button>
        </div>

        {error && (
          <div id="upload-error" role="alert" className="rounded-lg border border-brand-destructive/40 bg-brand-bg p-3 text-sm text-brand-destructive">
            {error}
          </div>
        )}

        {step === STEPS.PICK && (
          <form onSubmit={handleParse} className="space-y-3">
            {/* Every control carries an id: the Selenium system tier selects by DOM id, so a
                control without one cannot be driven from a browser test. */}
            <label htmlFor="upload-learner" className="block text-sm font-medium text-brand-fg">
              Learner
              <select
                id="upload-learner"
                value={learnerId}
                onChange={(e) => setLearnerId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-brand-border p-2 text-sm"
              >
                {learners.map((l) => (
                  <option key={l.id} value={l.id}>{l.pseudonym}</option>
                ))}
              </select>
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label htmlFor="upload-semester" className="block text-sm font-medium text-brand-fg">
                Semester
                <select
                  id="upload-semester"
                  value={semester}
                  onChange={(e) => setSemester(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-brand-border p-2 text-sm"
                >
                  {semesters.length === 0 && <option value="">Loading…</option>}
                  {semesters.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <p className="mt-0.5 text-[11px] text-brand-fg-muted">
                  Which semester these marks belong to
                </p>
              </label>

              <label htmlFor="upload-band" className="block text-sm font-medium text-brand-fg">
                Band
                <select
                  id="upload-band"
                  value={band}
                  onChange={(e) => setBand(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-brand-border p-2 text-sm"
                >
                  <option value="">Not recorded</option>
                  {BAND_OPTIONS.map((b) => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </select>
                <p className="mt-0.5 text-[11px] text-brand-fg-muted">
                  The paper sat — the rubric differs by band
                </p>
              </label>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {METRIC_KEYS.map((key) => {
                const err = metricErrors[key];
                const spec = specFor(key);
                return (
                  <label key={key} htmlFor={`upload-${key}`} className="block text-sm font-medium text-brand-fg">
                    {spec?.label ?? key}
                    <input
                      id={`upload-${key}`}
                      type="text"
                      inputMode="decimal"
                      value={metrics[key]}
                      onChange={(e) => updateMetric(key, e.target.value)}
                      onFocus={(e) => e.target.select()}
                      aria-invalid={!!err}
                      className={`mt-1 w-full rounded-lg border-2 p-2 text-sm outline-none transition-colors ${
                        err
                          ? "border-brand-destructive focus:border-brand-destructive"
                          : "border-brand-border focus:border-brand-primary"
                      }`}
                    />
                    <p className="mt-0.5 text-[11px] text-brand-fg-muted">
                      {spec ? `Valid range: 0–${spec.max}` : "Valid range: 0–…"}
                      {" · leave blank if not assessed"}
                    </p>
                    {err && (
                      <p className="mt-0.5 text-[11px] font-medium text-brand-destructive">{err}</p>
                    )}
                  </label>
                );
              })}
            </div>

            <label htmlFor="upload-file" className="block text-sm font-medium text-brand-fg">
              Assessment file (PDF or DOCX)
              <input
                id="upload-file"
                type="file"
                accept=".pdf,.docx"
                onChange={(e) => setFile(e.target.files[0])}
                className="mt-1 w-full text-sm"
              />
            </label>

            <Button type="submit" disabled={!file || loading || hasInvalidMetric}>
              {loading ? "Parsing…" : "Parse report"}
            </Button>
          </form>
        )}

        {step === STEPS.PREVIEW && preview && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-sm text-brand-fg-muted">Semester</p>
                <p className="text-lg font-semibold text-brand-fg">{semester}</p>
              </div>
              <div>
                <p className="text-sm text-brand-fg-muted">Band</p>
                <p className="text-lg font-semibold text-brand-fg">{band || "Not recorded"}</p>
              </div>
              {METRIC_KEYS.map((key) => (
                <div key={key}>
                  <p className="text-sm text-brand-fg-muted">{specFor(key)?.label ?? key}</p>
                  {/* An empty field reads as "Not assessed", not as 0 — the therapist should see
                      the same distinction on the confirmation card that the database records. */}
                  <p className="text-lg font-semibold text-brand-fg">
                    {metrics[key] === "" ? "Not assessed" : metrics[key]}
                  </p>
                </div>
              ))}
            </div>

            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-brand-fg-muted">
                  <th className="pb-1">Task</th>
                  <th className="pb-1">Score</th>
                  <th className="pb-1">Max score</th>
                </tr>
              </thead>
              <tbody>
                {preview.tasks.map((t) => (
                  <tr key={t.name} className="border-t border-brand-border">
                    <td className="py-1">{t.name}</td>
                    <td className="py-1">{t.score}</td>
                    <td className="py-1">{t.max_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="font-medium text-brand-fg">Strengths</p>
                <ul className="list-disc pl-4 text-brand-fg-muted">
                  {preview.strengths.map((s) => <li key={s}>{s}</li>)}
                </ul>
              </div>
              <div>
                <p className="font-medium text-brand-fg">Weaknesses</p>
                <ul className="list-disc pl-4 text-brand-fg-muted">
                  {preview.weaknesses.map((w) => <li key={w}>{w}</li>)}
                </ul>
              </div>
            </div>

            {preview.notes && <p className="text-xs italic text-brand-fg-muted">{preview.notes}</p>}

            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setStep(STEPS.PICK)}>Back</Button>
              <Button onClick={handleConfirm} disabled={loading}>
                {loading ? "Saving…" : "Confirm & save"}
              </Button>
            </div>
          </div>
        )}

        {step === STEPS.DONE && (
          <div className="space-y-3 text-center">
            <p className="text-brand-fg">Data saved successfully.</p>
            <Button onClick={onClose}>Close</Button>
          </div>
        )}
      </Card>
    </div>
  );
}