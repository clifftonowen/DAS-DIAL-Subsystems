import { useState } from "react";
import { supabase } from "../lib/supabase";

// Uploads a student writing sample to POST /assessments/upload (multipart).
export default function UploadView({ learnerId }) {
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("");

  async function submit(e) {
    e.preventDefault();
    if (!file) return;
    const { data } = await supabase.auth.getSession();
    const form = new FormData();
    form.append("learner_id", learnerId);
    form.append("file", file);
    const res = await fetch(`${import.meta.env.VITE_API_URL}/assessments/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${data?.session?.access_token}` },
      body: form,
    });
    setStatus(res.ok ? "Uploaded" : `Error ${res.status}`);
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg bg-white p-4 shadow-sm">
      <input type="file" onChange={(e) => setFile(e.target.files[0])} />
      <button className="rounded bg-slate-900 px-3 py-1 text-sm text-white">Upload sample</button>
      {status && <p className="text-sm text-slate-500">{status}</p>}
    </form>
  );
}
