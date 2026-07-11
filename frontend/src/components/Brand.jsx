export default function Brand({ size = "md" }) {
  const text = size === "lg" ? "text-2xl" : "text-lg";
  return (
    <div className="flex items-center gap-2">
      <svg
        width="28"
        height="28"
        viewBox="0 0 28 28"
        fill="none"
        aria-hidden="true"
        className="shrink-0"
      >
        <rect width="28" height="28" rx="8" className="fill-brand-primary" />
        <path
          d="M8 19V9h4.2a5 5 0 0 1 0 10H8Zm2.6-2.3h1.6a2.7 2.7 0 0 0 0-5.4h-1.6v5.4Z"
          className="fill-brand-on-primary"
        />
        <circle cx="20.5" cy="9.5" r="1.8" className="fill-brand-secondary" />
      </svg>
      <span className={`font-display font-bold tracking-tight text-brand-fg ${text}`}>
        DAS D.I.A.L
      </span>
    </div>
  );
}
