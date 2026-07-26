// HeroBanner.jsx — Welcome banner at the top of the Main page.
// Pure presentational — no state, no data fetching.
//
// Implements the hero from "Dashboard Color Refresh" (direction 1d, Crisp Bright):
// a flat pale-rose surface with the text block on the left, a two-circle cluster
// on the right, and a large accent circle bleeding off the top-right corner.
//
// Props:
//   dateLabel     {string} — formatted date line above the greeting
//   onStartReview {func}   — click handler for the "Start review" button

export default function HeroBanner({ dateLabel, onStartReview }) {
  return (
    <div className="relative flex items-center justify-between overflow-hidden
                    rounded-[20px] bg-brand-hero-bg px-[30px] py-[26px] text-brand-hero-text">

      {/* ── Text block ── */}
      <div className="relative z-[2]">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] opacity-[0.72]">
          {dateLabel}
        </p>
        <p className="text-[17px] font-medium opacity-90">Welcome back to your</p>
        <h1 className="mb-4 mt-0.5 text-[34px] font-extrabold leading-[1.05] tracking-[-0.02em]">
          Daily dashboard
        </h1>
        <button
          onClick={onStartReview}
          className="rounded-full bg-brand-primary px-[22px] py-[11px] text-sm font-semibold
                     text-brand-on-primary transition-colors hover:bg-brand-primary-hover"
        >
          Start review
        </button>
      </div>

      {/* ── Decorative circle cluster, right side ── */}
      <div aria-hidden="true" className="relative z-[2] flex items-center gap-3.5 pr-3">
        <span className="h-16 w-16 rounded-full bg-brand-hero-accent opacity-90" />
        <span className="h-24 w-24 rounded-full bg-brand-primary opacity-[0.14]" />
      </div>

      {/* ── Accent circle bleeding off the top-right corner ── */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -right-10 -top-10 h-[150px] w-[150px]
                   rounded-full bg-brand-hero-accent opacity-[0.22]"
      />
    </div>
  );
}
