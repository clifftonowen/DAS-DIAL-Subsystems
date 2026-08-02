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
    // shrink-0: the banner is overflow-hidden, so if a flex parent ever compresses
    // it the content is clipped rather than scrolled. It sizes to its content.
    <div className="relative flex shrink-0 items-center justify-between gap-6 overflow-hidden
                    rounded-[20px] bg-brand-hero-bg px-[30px] py-[26px] text-brand-hero-text">

      {/* ── Text block ── */}
      {/* min-w-0 lets this shrink below its content width instead of pushing the
          circles out of the rounded corner on narrow viewports. */}
      <div className="relative z-[2] min-w-0">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] opacity-[0.72]">
          {dateLabel}
        </p>
        <p className="text-[17px] font-medium opacity-90">Welcome back to your</p>
        <h1 className="mb-4 mt-0.5 text-[28px] font-extrabold leading-[1.05] tracking-[-0.02em] sm:text-[34px]">
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
      {/* Purely decorative and fixed-size, so it is dropped rather than allowed to
          crowd the text on narrow viewports. */}
      <div aria-hidden="true" className="relative z-[2] hidden shrink-0 items-center gap-3.5 pr-3 sm:flex">
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
