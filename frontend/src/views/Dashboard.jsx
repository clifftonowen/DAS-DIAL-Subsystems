import { useEffect, useState } from "react";
import { listLearners } from "../lib/api";
import Button from "../components/Button";
import Card from "../components/Card";
import Navbar from "../components/Navbar";
import UploadView from "./UploadView";

function LearnerCardSkeleton() {
  return (
    <Card className="flex animate-pulse items-center justify-between">
      <div className="space-y-2">
        <div className="h-4 w-32 rounded bg-brand-muted" />
        <div className="h-3 w-20 rounded bg-brand-muted" />
      </div>
      <div className="flex gap-2">
        <div className="h-9 w-24 rounded-lg bg-brand-muted" />
        <div className="h-9 w-32 rounded-lg bg-brand-muted" />
      </div>
    </Card>
  );
}

export default function Dashboard({ session }) {
  const [view, setView] = useState("learners");
  const [learners, setLearners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    listLearners()
      .then(setLearners)
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-dvh bg-brand-bg">
      <Navbar view={view} onViewChange={setView} session={session} />
      <main className="mx-auto max-w-4xl space-y-6 p-6">
        {view === "learners" ? (
          <>
            <div>
              <h1 className="font-display text-2xl font-bold text-brand-fg">Learners</h1>
              <p className="text-sm text-brand-fg-muted">
                {loading ? "Loading…" : `${learners.length} learner${learners.length === 1 ? "" : "s"}`}
              </p>
            </div>

            {err && (
              <Card role="alert" className="border-brand-destructive/40 bg-brand-bg text-brand-destructive">
                {err}
              </Card>
            )}

            {loading && (
              <div className="grid gap-3">
                <LearnerCardSkeleton />
                <LearnerCardSkeleton />
                <LearnerCardSkeleton />
              </div>
            )}

            {!loading && !err && learners.length === 0 && (
              <Card className="text-center text-brand-fg-muted">
                No learners yet. Seed the DB or upload assessments.
              </Card>
            )}

            {!loading && learners.length > 0 && (
              <div className="grid gap-3">
                {learners.map((l) => (
                  <Card key={l.id} className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-brand-fg">{l.pseudonym}</p>
                      <span className="inline-block rounded-full bg-brand-muted px-2 py-0.5 text-xs font-medium text-brand-fg-muted">
                        {l.band_level}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium text-brand-fg-muted">Coming soon</span>
                      <Button
                        variant="secondary"
                        disabled
                        title="Generate Profile — Subsystem 2, next iteration"
                      >
                        Generate Profile
                      </Button>
                      <Button
                        variant="secondary"
                        disabled
                        title="Generate Activity — Subsystem 3, next iteration"
                      >
                        Generate Activity
                      </Button>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </>
        ) : (
          <UploadView />
        )}
      </main>
    </div>
  );
}
