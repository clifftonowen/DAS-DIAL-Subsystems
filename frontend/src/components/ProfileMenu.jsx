// ProfileMenu.jsx — top-right profile dropdown for the dashboard header.
//
// Ported from the skylar_navbar_and_profile branch's Navbar. Self-contained:
// takes the Supabase `session` and renders an avatar + "My Profile" menu that
// reveals the signed-in email and a Sign out action. Opens toward the right
// edge (right-0) since it lives at the top-right of the header.

import { useState, useRef, useEffect } from "react";
import { supabase } from "../lib/supabase";

export default function ProfileMenu({ session }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const email = session?.user?.email ?? "";
  const initial = email.charAt(0).toUpperCase();

  // Close the dropdown when clicking anywhere outside it.
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
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
        <div className="absolute right-0 top-full mt-1 w-max max-w-xs rounded-lg border border-brand-border bg-white p-3 shadow-lg">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-primary text-sm font-bold text-brand-on-primary">
              {initial}
            </span>
            <span className="text-sm break-all text-brand-fg">{email}</span>
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
  );
}
