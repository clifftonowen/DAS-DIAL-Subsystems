import { useState, useRef, useEffect } from "react";
import { supabase } from "../lib/supabase";
import Brand from "./Brand";

const links = [
  { key: "learners", label: "Learners" },
  { key: "upload", label: "Upload" },
];

export default function Navbar({ view, onViewChange, session }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const email = session?.user?.email ?? "";
  const initial = email.charAt(0).toUpperCase();

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <header className="sticky top-0 z-10 border-b border-brand-border bg-white">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
        <div className="flex items-center gap-2">
          <div className="relative" ref={ref}>
            <button
              onClick={() => setOpen((o) => !o)}
              className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1 text-sm font-medium text-brand-fg-muted hover:bg-brand-muted hover:text-brand-fg"
            >
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-primary text-xs font-bold text-brand-on-primary">
                {initial}
              </span>
              My Profile
            </button>
            {open && (
              <div className="absolute left-0 top-full mt-1 w-48 rounded-lg border border-brand-border bg-white p-3 shadow-lg">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-primary text-sm font-bold text-brand-on-primary">
                    {initial}
                  </span>
                  <span className="truncate text-sm text-brand-fg">{email}</span>
                </div>
                <span
                  onClick={() => supabase.auth.signOut()}
                  className="mt-3 block cursor-pointer text-sm text-brand-fg-muted hover:text-brand-fg"
                >
                  Sign out
                </span>
              </div>
            )}
          </div>
          <Brand />
        </div>
        <nav className="flex items-center gap-1">
          {links.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => onViewChange(key)}
              className={`relative rounded-lg px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer
                ${view === key
                  ? "text-brand-primary"
                  : "text-brand-fg-muted hover:text-brand-fg hover:bg-brand-muted"}`}
            >
              {label}
              {view === key && (
                <span className="absolute bottom-0 left-1/2 h-0.5 w-4 -translate-x-1/2 rounded-full bg-brand-primary" />
              )}
            </button>
          ))}
        </nav>
      </div>
    </header>
  );
}
