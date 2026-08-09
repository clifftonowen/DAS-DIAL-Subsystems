// Modal.jsx — generic overlay shell: dimmed backdrop, centred panel, Escape and
// click-outside to close.
//
// Deliberately knows nothing about what it contains, so the layering stays right:
// views compose this with whatever they want to show. ShareWindow.jsx has its own
// near-identical copy of this markup and could adopt this later.
//
// Props:
//   onClose  {function}  Escape key, backdrop click, and the corner button
//   labelledBy {string}  id of the element naming the dialog, for screen readers
//   className {string}   extra classes on the panel (e.g. a wider max-width)
//   children

import { useEffect, useRef } from "react";

export default function Modal({ onClose, labelledBy, className = "", children }) {
  const panelRef = useRef(null);

  useEffect(() => {
    // Focus moves into the panel so Escape and Tab act on the overlay rather than
    // the page still rendered behind it.
    panelRef.current?.focus();

    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);

    // The page behind must not scroll while the overlay is open.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto bg-black/60 p-4 sm:p-8"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        // Clicks inside must not reach the backdrop's onClose.
        onClick={(e) => e.stopPropagation()}
        className={`relative w-full max-w-4xl rounded-2xl border border-brand-border bg-white p-6 shadow-xl outline-none ${className}`}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 z-10 flex h-9 w-9 items-center justify-center rounded-lg text-xl leading-none text-brand-fg-muted transition-colors hover:bg-brand-muted hover:text-brand-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-ring/40"
        >
          ×
        </button>
        {children}
      </div>
    </div>
  );
}
