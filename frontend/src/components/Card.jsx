export default function Card({ className = "", children, ...props }) {
  return (
    <div
      className={`rounded-xl border border-brand-border bg-white p-4 shadow-sm ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
