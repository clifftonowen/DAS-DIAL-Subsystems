import { useState } from "react";
import { supabase } from "../lib/supabase";
import Brand from "../components/Brand";
import Button from "../components/Button";
import Card from "../components/Card";

export default function AuthView({ onAuthed }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [mode, setMode] = useState("login");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    setSubmitting(true);

    const { data, error } =
      mode === "login"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });

    setSubmitting(false);

    if (error) {
      setError(error.message);
      return;
    }
    if (mode === "signup" && !data.session) {
      setNotice("Check your email to confirm your account, then log in.");
      setMode("login");
      return;
    }
    onAuthed?.();
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-brand-bg px-4">
      <Card className="w-full max-w-sm space-y-5 p-6">
        <div className="space-y-1">
          <Brand size="lg" />
          <p className="text-sm text-brand-fg-muted">
            {mode === "login" ? "Log in to your therapist account" : "Create a therapist account"}
          </p>
        </div>

        <form onSubmit={submit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <label htmlFor="email" className="block text-sm font-medium text-brand-fg">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              className="min-h-11 w-full rounded-lg border border-brand-border bg-white px-3 text-base text-brand-fg
                focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-ring/40"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="password" className="block text-sm font-medium text-brand-fg">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
                minLength={6}
                className="min-h-11 w-full rounded-lg border border-brand-border bg-white px-3 pr-11 text-base text-brand-fg
                  focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-ring/40"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-brand-fg-muted
                  hover:text-brand-fg focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-ring/40 rounded-lg cursor-pointer"
              >
                {showPassword ? (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M3 3l18 18M10.6 10.6a2 2 0 002.8 2.8M9.9 5.1A10.9 10.9 0 0112 5c5 0 9 4 10 7-.3 1-1 2.2-2 3.3M6.5 6.7C4.6 8 3.3 9.8 2 12c1 3 5 7 10 7 1.4 0 2.7-.3 3.9-.8"
                      stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M2 12c1-3 5-7 10-7s9 4 10 7c-1 3-5 7-10 7s-9-4-10-7Z"
                      stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                    <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          {error && (
            <p role="alert" className="text-sm font-medium text-brand-destructive">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="text-sm font-medium text-brand-success">
              {notice}
            </p>
          )}

          <Button type="submit" variant="primary" loading={submitting} className="w-full">
            {submitting
              ? mode === "login" ? "Signing in…" : "Signing up…"
              : mode === "login" ? "Log in" : "Sign up"}
          </Button>

          <Button
            type="button"
            variant="ghost"
            className="w-full"
            onClick={() => {
              setMode(mode === "login" ? "signup" : "login");
              setError("");
              setNotice("");
            }}
          >
            {mode === "login" ? "Need an account? Sign up" : "Have an account? Log in"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
