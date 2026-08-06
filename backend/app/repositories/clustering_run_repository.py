"""Data access for `clustering_runs` — one row per k-means fit (Subsystem 2).

Describes MODELS, not learners, which is why it survived the merge of `learner_scores` into
`learners` untouched: a run is a statement about a fit (its features, its k, the silhouette
sweep behind that k), and the learners it labelled are identified only by the labels it wrote
onto them.
"""
from app.repositories.base import BaseRepository


class ClusteringRunRepository(BaseRepository):
    table = "clustering_runs"

    def save_many(self, runs: list[dict]) -> int:
        self.db.insert(runs).execute()
        return len(runs)

    def latest_by_scope_and_tier(self) -> list[dict]:
        """The newest run for each (scope, tier) — the cohort model plus one per band group.

        Ingest appends rather than overwrites, so older fits stay inspectable in the table and
        the de-duplication happens here. Rows arrive newest-first, so the first sighting of a
        key is the one to keep.

        Keyed on the pair, not on tier alone: the two scopes are separate models and a future
        scope could reuse a tier name. Ordered cohort-first, then bands alphabetically, which
        is the order the dashboard's comparison caption reads in.
        """
        rows = self.db.select("*").order("created_at", desc=True).execute().data or []
        newest: dict[tuple, dict] = {}
        for row in rows:
            newest.setdefault((row.get("scope"), row.get("tier")), row)
        return [
            newest[key]
            for key in sorted(newest, key=lambda k: (k[0] != "cohort", str(k[0]), str(k[1])))
        ]
