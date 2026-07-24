import { useState } from "react";
import { previewAssessment, confirmAssessment } from "../lib/api";
import Card from "../components/Card";
import Button from "../components/Button";

const STEPS = { PICK: "pick", PREVIEW: "preview", DONE: "done" };

export default function UploadView({ learners, onClose, onSaved }) {
  const [learnerId, setLearnerId] = useState(learners[0]?.id ?? "");
  const [file, setFile] = useState(null);
  const [step, setStep] = useState(STEPS.PICK);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleParse(e) {
    e.preventDefault();
    if (!file || !learnerId) return;
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
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/70 p-4">
      <Card className="w-full max-w-lg space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-bold text-brand-fg">Upload Assessment Data</h2>
          <button onClick={onClose} className="text-brand-fg-muted hover:text-brand-fg">✕</button>
        </div>

        {error && (
          <div role="alert" className="rounded-lg border border-brand-destructive/40 bg-brand-bg p-3 text-sm text-brand-destructive">
            {error}
          </div>
        )}

        {step === STEPS.PICK && (
          <form onSubmit={handleParse} className="space-y-3">
            <label className="block text-sm font-medium text-brand-fg">
              Learner
              <select
                value={learnerId}
                onChange={(e) => setLearnerId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-brand-border p-2 text-sm"
              >
                {learners.map((l) => (
                  <option key={l.id} value={l.id}>{l.pseudonym}</option>
                ))}
              </select>
            </label>

            <label className="block text-sm font-medium text-brand-fg">
              Assessment file (PDF or DOCX)
              <input
                type="file"
                accept=".pdf,.docx"
                onChange={(e) => setFile(e.target.files[0])}
                className="mt-1 w-full text-sm"
              />
            </label>

            <Button type="submit" disabled={!file || loading}>
              {loading ? "Parsing…" : "Parse report"}
            </Button>
          </form>
        )}

        {step === STEPS.PREVIEW && preview && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-sm text-brand-fg-muted">Confidence score</p>
                <p className="text-lg font-semibold text-brand-fg">{preview.confidence_score}</p>
              </div>
              <div>
                <p className="text-sm text-brand-fg-muted">Risk score</p>
                <p className="text-lg font-semibold text-brand-fg">{preview.risk_score}</p>
              </div>
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

            {preview.notes && (
              <p className="text-xs italic text-brand-fg-muted">{preview.notes}</p>
            )}

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