"""CohortService - Subsystem 2 read side.

Serves the clustered cohort to the analytics dashboard. Clustering itself happens offline in
`scripts/ingest_dial_data.py`; by the time a request arrives the labels are already columns on
`learners`, so this is a read and a reshape. Nothing here imports scikit-learn — the API process
never fits a model.

Reads `learners`, which since the 2026-08-07 merge holds both the therapist's caseload and the
anonymised research cohort. The scatter plots BOTH: a caseload learner with DIAL marks is a
point like any other, and `on_caseload` rides along so the cluster table can mark them.
"""
from app.repositories.clustering_run_repository import ClusteringRunRepository
from app.repositories.learner_repository import LearnerRepository
from app.schemas.dto import CohortClusters, CohortLearner, ClusteringRunOut


class CohortService:
    def __init__(self):
        self.learners = LearnerRepository()
        self.runs = ClusteringRunRepository()

    def get_clusters(self) -> CohortClusters:
        rows = self.learners.list_cohort()
        learners = [self._to_learner(row) for row in rows]

        return CohortClusters(
            learners=learners,
            runs=[self._to_run(run) for run in self.runs.latest_by_scope_and_tier()],
            # Counted per scope in one pass: the dashboard reports "n learners hidden" for
            # whichever view is active, and the two differ.
            unclustered={
                "cohort": sum(1 for x in learners if x.cluster_cohort is None),
                "band": sum(1 for x in learners if x.cluster_band is None),
            },
        )

    # ── helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _to_learner(row: dict) -> CohortLearner:
        return CohortLearner(
            id=str(row["id"]),
            student_id=row.get("student_id"),
            # Cohort rows are anonymised, so the workbook id IS the name. A caseload learner
            # has a real pseudonym and the table shows that instead.
            pseudonym=row.get("pseudonym") or "",
            on_caseload=bool(row.get("on_caseload")),
            band=row.get("band"),
            band_group=row.get("band_group"),
            cluster_band=row.get("cluster_band"),
            cluster_cohort=row.get("cluster_cohort"),
            writing_genre=row.get("writing_genre"),
            phonics=row.get("phonics"),
            word_reading_accuracy=row.get("word_reading_accuracy"),
            word_spelling=row.get("word_spelling"),
            writing=row.get("writing"),
        )

    @staticmethod
    def _to_run(row: dict) -> ClusteringRunOut:
        # jsonb keys are strings coming back from Postgres, but a run written by an in-process
        # fake (or by a test) may still carry int keys — normalise so the DTO validates either way.
        sweep = row.get("silhouette_by_k") or {}
        return ClusteringRunOut(
            # Defaulted rather than required: rows written before the scope column existed
            # carry the band models, which is what the column's SQL default says too.
            scope=row.get("scope") or "band",
            tier=row.get("tier", ""),
            features=row.get("features") or [],
            k=row.get("k", 0),
            best_silhouette=row.get("best_silhouette", 0.0),
            silhouette_by_k={str(k): float(v) for k, v in sweep.items()},
            n_learners=row.get("n_learners", 0),
        )
