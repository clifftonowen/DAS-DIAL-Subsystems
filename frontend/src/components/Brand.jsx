export default function Brand({ size = "md" }) {
  const text = size === "lg" ? "text-2xl" : "text-lg";
  const mark = size === "lg" ? "h-9 w-9" : "h-7 w-7";
  return (
    <div className="flex items-center gap-2">
      <img src="/das-logo.png" alt="" className={`shrink-0 object-contain ${mark}`} />
      <span className={`font-display font-bold tracking-tight text-brand-fg ${text}`}>
        DAS D.I.A.L
      </span>
    </div>
  );
}
