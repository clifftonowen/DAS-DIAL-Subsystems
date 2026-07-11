import { useState } from "react";
import { supabase } from "../lib/supabase";

export default function AuthView({ onAuthed }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState("login");
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setError("");
    const fn = mode === "login" ? supabase.auth.signInWithPassword : supabase.auth.signUp;
    const { error } = await fn({ email, password });
    if (error) setError(error.message);
    else onAuthed?.();
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <form onSubmit={submit} className="w-80 space-y-4 rounded-xl bg-white p-6 shadow">
        <h1 className="text-xl font-semibold">DAS D.I.A.L</h1>
        <p className="text-sm text-slate-500">Therapist {mode}</p>
        <input className="w-full rounded border p-2" placeholder="Email"
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className="w-full rounded border p-2" type="password" placeholder="Password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className="w-full rounded bg-slate-900 p-2 text-white">
          {mode === "login" ? "Log in" : "Sign up"}
        </button>
        <button type="button" className="w-full text-sm text-slate-500"
          onClick={() => setMode(mode === "login" ? "signup" : "login")}>
          {mode === "login" ? "Need an account? Sign up" : "Have an account? Log in"}
        </button>
      </form>
    </div>
  );
}
