import { useEffect, useState } from "react";
import { listLearners, generateProfile, generateActivity } from "../lib/api";
import { supabase } from "../lib/supabase";

export default function Dashboard() {
  const [learners, setLearners] = useState([]);
  const [output, setOutput] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => { listLearners().then(setLearners).catch((e) => setErr(e.message)); }, []);

  async function runProfile(id) {
    setErr("");
    try { setOutput(await generateProfile(id)); } catch (e) { setErr(e.message); }
  }
  async function runActivity(id) {
    setErr("");
    try { setOutput(await generateActivity(id, { literacy_objective: "decoding", level: "Band A" })); }
    catch (e) { setErr(e.message); }
  }

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Learners</h1>
        <button className="text-sm text-slate-500" onClick={() => supabase.auth.signOut()}>Sign out</button>
      </header>
      {err && <p className="mb-4 text-sm text-red-600">{err}</p>}
      <div className="grid gap-3">
        {learners.length === 0 && <p className="text-slate-500">No learners yet. Seed the DB or upload assessments.</p>}
        {learners.map((l) => (
          <div key={l.id} className="flex items-center justify-between rounded-lg bg-white p-4 shadow-sm">
            <div><p className="font-medium">{l.pseudonym}</p><p className="text-sm text-slate-500">{l.band_level}</p></div>
            <div className="flex gap-2">
              <button className="rounded bg-slate-200 px-3 py-1 text-sm" onClick={() => runProfile(l.id)}>Profile</button>
              <button className="rounded bg-slate-900 px-3 py-1 text-sm text-white" onClick={() => runActivity(l.id)}>Generate activity</button>
            </div>
          </div>
        ))}
      </div>
      {output && (
        <pre className="mt-6 overflow-auto rounded-lg bg-slate-900 p-4 text-xs text-slate-100">
          {JSON.stringify(output, null, 2)}
        </pre>
      )}
    </div>
  );
}
