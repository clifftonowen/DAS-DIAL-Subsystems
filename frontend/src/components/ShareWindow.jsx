// ShareWindow.jsx — the pop up window for Share Learning Activity.
//
// Owns the therapist-facing side of the sequence diagram: collect the recipient
// address, call shareActivity(), then show one of three outcomes.
// outcomes: Idle, sending, sent, error
// Email format is checked here as well as on the server. The client check instant re-entry without a round trip and the server check is what actually protects the send, since anyone can post to the API directly.
//
// Props:
//   activityId  {string}   activity to share; window refuses to open without one
//   activityName{string}   shown in the header for confirmation
//   onClose     {function} called when the therapist closes the window

import { useEffect, useRef, useState } from "react";
import Button from "./Button";
import { shareActivity } from "../lib/api";

// EMAIL_RE in share_service.py
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

// this status is found in share.py
const RETRIABLE = (status) => status !== 400 && status !== 422;

export default function ShareWindow({ activityId, activityName = "this activity", onClose }) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("idle");   // idle | sending | sent | error
  const [error, setError] = useState(null);       
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && status !== "sending" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, status]);

  async function send() {
    const recipient = email.trim();

    // Flow 1a — reject the input and prompt re-entry without calling the server
    if (!EMAIL_RE.test(recipient)) {
      setError({ message: "Invalid email address, please re-enter", retriable: false });
      setStatus("error");
      inputRef.current?.focus();
      return;
    }

    setStatus("sending");
    setError(null);
    try {
      await shareActivity(activityId, recipient);
      setStatus("sent");
    } catch (err) {
      setError({ message: err.message, retriable: RETRIABLE(err.status) });
      setStatus("error");
    }
  }

  function onSubmit(e) {
    e.preventDefault();
    send();
  }

  const busy = status === "sending";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={() => !busy && onClose()}
    >
      <div
        role="window"
        aria-modal="true"
        aria-labelledby="share-window-title"
        className="w-full max-w-md rounded-2xl border border-brand-border bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="share-window-title" className="text-lg font-semibold text-brand-fg">
          Share activity
        </h2>
        <p className="mt-1 text-sm text-brand-fg-muted">
          {status === "sent"
            ? "The recipient has been emailed a PDF copy."
            : <>Email a PDF of <span className="font-medium text-brand-fg">{activityName}</span> to a parent or colleague.</>}
        </p>

        {status === "sent" ? (
          <>
            <div className="mt-5 rounded-lg border border-green-200 bg-green-50 p-4">
              <p className="text-sm font-medium text-green-800">Activity sent to recipient</p>
              <p className="mt-1 text-sm text-green-700 break-all">{email.trim()}</p>
            </div>
            <div className="mt-5 flex justify-end">
              <Button variant="primary" onClick={onClose}>Done</Button>
            </div>
          </>
        ) : (
          <form onSubmit={onSubmit}>
            <label htmlFor="share-email" className="mt-5 block text-sm font-medium text-brand-fg">
              Recipient email
            </label>
            <input
              id="share-email"
              ref={inputRef}
              type="email"
              value={email}
              disabled={busy}
              onChange={(e) => {
                setEmail(e.target.value);
                if (status === "error") setStatus("idle");   
              }}
              placeholder="parent@example.com"
              aria-invalid={status === "error" || undefined}
              aria-describedby={status === "error" ? "share-error" : undefined}
              className={`mt-1.5 h-11 w-full rounded-lg border-2 px-3 text-sm outline-none transition-colors
                disabled:bg-brand-muted disabled:text-brand-fg-muted
                ${status === "error" ? "border-red-400 focus:border-red-500" : "border-brand-border focus:border-brand-primary"}`}
            />

            {status === "error" && (
              <div id="share-error" role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3">
                <p className="text-sm text-red-800">{error.message}</p>
                {!error.retriable && error.message !== "Invalid email address, please re-enter" && (
                  <p className="mt-1 text-xs text-red-700">
                    This activity cannot be exported, so the share was cancelled.
                  </p>
                )}
              </div>
            )}

            <div className="mt-5 flex justify-end gap-2.5">
              <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" loading={busy} disabled={busy || !email.trim()}>
                {busy ? "Sending…" : error?.retriable ? "Retry" : "Send"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

