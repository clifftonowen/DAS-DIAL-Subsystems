const variants = {
  primary:
    "bg-brand-primary text-brand-on-primary hover:bg-brand-fg disabled:hover:bg-brand-primary",
  secondary:
    "bg-brand-muted text-brand-fg hover:bg-brand-border disabled:hover:bg-brand-muted",
  ghost:
    "bg-transparent text-brand-fg hover:bg-brand-muted disabled:hover:bg-transparent",
};

export default function Button({
  variant = "primary",
  loading = false,
  disabled = false,
  className = "",
  children,
  ...props
}) {
  const isDisabled = disabled || loading;
  return (
    <button
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium
        transition-colors duration-200 cursor-pointer
        focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-ring/40
        disabled:cursor-not-allowed disabled:opacity-50 active:scale-[0.98]
        ${variants[variant]} ${className}`}
      {...props}
    >
      {loading && (
        <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
      )}
      {children}
    </button>
  );
}
