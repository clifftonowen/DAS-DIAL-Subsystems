import { useState } from "react";
import { logIn as apiLogIn, signUp as apiSignUp } from "../lib/api";
import { supabase } from "../lib/supabase";
import Brand from "../components/Brand";
import Button from "../components/Button";
import Card from "../components/Card";

/**
 * AuthView — the primary actor's boundary for UC6 Log In and UC8 Sign Up.
 *
 * Both flows go through AuthController (`POST /auth/login`, `POST /auth/signup`)
 * rather than calling Supabase directly, so the AuthView -> AuthController message
 * in the sequence diagrams is a real request. The tokens the backend returns are
 * handed to `supabase.auth.setSession`, which is what fires `onAuthStateChange`
 * in main.jsx and populates the session that `lib/api.js`'s authHeader() reads
 * before every subsequent request.
 */
// Demo mode. Both set => this is the public deployment: show the seeded credentials and hide the
// sign-up toggle, because the backend answers 403 there (SIGNUP_ENABLED=false) and offering a
// button that cannot work is worse than not offering it.
//
// The password is deliberately in the bundle. It guards a read-only demo account on a public
// resume link, so it is a doorbell, not a lock — anyone who can read the page is who it is for.
// Deriving demo mode from these two rather than adding a separate VITE_SIGNUP_ENABLED keeps it
// one concept: either there is a demo account to show or there is not.
const DEMO_EMAIL = import.meta.env.VITE_DEMO_EMAIL;
const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD;
const DEMO_MODE = Boolean(DEMO_EMAIL && DEMO_PASSWORD);

export default function AuthView({ onAuthed }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [mode, setMode] = useState("login");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // UC6: AuthView -> AuthController logIn(email, password)
  async function logIn(email, password) {
    const session = await apiLogIn(email, password);
    await supabase.auth.setSession({
      access_token: session.access_token,
      refresh_token: session.refresh_token,
    });
    onAuthed?.();
  }

  // UC8: AuthView -> AuthController signUp(email, password)
  async function signUp(email, password) {
    const result = await apiSignUp(email, password);
    if (result.email_confirmation_required || !result.access_token) {
      // The account exists but no session was issued yet, so the therapist stays
      // signed out until they confirm — UC8's postcondition.
      setNotice("Account is successfully created. Check your email to confirm, then log in.");
      setMode("login");
      return;
    }
    await supabase.auth.setSession({
      access_token: result.access_token,
      refresh_token: result.refresh_token,
    });
    onAuthed?.();
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    setSubmitting(true);
    try {
      if (mode === "login") await logIn(email, password);
      else await signUp(email, password);
    } catch (err) {
      // api.js surfaces FastAPI's `detail`, so this is the message AuthController sent.
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
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

        {DEMO_MODE && (
          <div className="space-y-2 rounded-lg border border-brand-border bg-brand-bg p-3">
            <p className="text-sm font-medium text-brand-fg">Demo account</p>
            <dl className="space-y-0.5 text-sm text-brand-fg-muted">
              <div className="flex gap-2">
                <dt className="shrink-0">Email</dt>
                <dd className="truncate font-mono text-brand-fg">{DEMO_EMAIL}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="shrink-0">Password</dt>
                <dd className="truncate font-mono text-brand-fg">{DEMO_PASSWORD}</dd>
              </div>
            </dl>
            {/* Fills the form rather than submitting it: the visitor still presses Log in, so
                what happens next is something they chose, and a failure is legible as a failed
                login rather than as a page that broke on load. */}
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              onClick={() => {
                setEmail(DEMO_EMAIL);
                setPassword(DEMO_PASSWORD);
                setError("");
                setNotice("");
              }}
            >
              Use demo credentials
            </Button>
          </div>
        )}

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

          {!DEMO_MODE && (
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
          )}
        </form>
      </Card>
    </div>
  );
}
