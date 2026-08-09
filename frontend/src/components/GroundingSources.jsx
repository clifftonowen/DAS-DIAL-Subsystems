// GroundingSources.jsx — which curriculum pages an activity was built from.
//
// Shown for as long as the activity exists, not just to whoever generated it: a therapist
// picking up a colleague's learner needs to see what the activity was grounded in before they
// approve it. That is why the backend stores this on the activity row rather than only
// returning it from the generation call.
//
// TWO SHAPES, because rows written before grounding was stored still have to render:
//   grounding   [{title, source, page, concept, stage, similarity}]  the full record
//   groundedOn  ["Rhyme Time (BandA.pdf p.14)", ...]                 the older text[] fallback
// The fallback has no concept, stage or similarity — there is nothing to show, so it shows
// nothing rather than inventing a zero.
//
// Props:
//   grounding  {array}  content.grounding from the activity row (may be undefined)
//   groundedOn {array}  grounded_on from the activity row (may be undefined)
//   query      {string} the retrieval query that found them (may be undefined)

export default function GroundingSources({ grounding, groundedOn, query }) {
  const rich = grounding?.length ? grounding : null;
  const plain = !rich && groundedOn?.length ? groundedOn : null;

  // An activity with no provenance at all renders no card — an empty "Grounding sources"
  // heading would claim the section exists and is simply empty, which is a different thing.
  if (!rich && !plain) return null;

  return (
    <div className="rounded-xl border border-brand-border bg-white p-5 shadow-sm">
      <p className="mb-3 text-sm font-semibold text-brand-fg">Grounding sources</p>

      <ul className="space-y-2.5">
        {rich
          ? rich.map((g, i) => (
              <li key={i} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-brand-fg">{g.title}</p>
                  <p className="text-[11px] text-brand-fg-muted">
                    {[g.source && `${g.source} p.${g.page ?? "?"}`, g.concept, g.stage]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                {typeof g.similarity === "number" && (
                  <span className="shrink-0 rounded bg-brand-muted px-2 py-0.5 text-[11px] font-medium text-brand-fg-muted">
                    {g.similarity.toFixed(2)}
                  </span>
                )}
              </li>
            ))
          : plain.map((label, i) => (
              <li key={i} className="text-[13px] font-medium text-brand-fg">
                {label}
              </li>
            ))}
      </ul>

      {query && (
        <p className="mt-3 text-[11px] text-brand-fg-muted">Query: “{query}”</p>
      )}
    </div>
  );
}
