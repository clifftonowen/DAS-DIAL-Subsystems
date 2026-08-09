"""LearnerOverviewService — everything LearnerDetailPage needs about one learner.

Serves GET /learners/{id}/overview: the learner's identity, the DIAL marks behind their radar
chart, and every sitting on record behind their progress chart.

TWO GRAINS, WHICH IS WHY THIS SERVICE EXISTS AT ALL
    the learner row    identity plus their CURRENT marks — one row per person
    learner_sittings   the same four marks per SEMESTER — the line chart's series

    There is no derivation left anywhere in here. The seven cognitive dimensions this service
    used to assemble were mock scaffolding; the system standardises on the four marks DAS
    measures, so a profile is read, not computed.

EVERY PART IS OPTIONAL
    A learner with no marks, no history, or neither is an ordinary state, not a failure — an
    app-created learner has none of it until UC1's upload adds a sitting, and one sitting is as
    valid as ten. Only an unknown learner raises, mirroring LearnerService.get_learner, which is
    the one absence the therapist can act on.
"""
from app.ingestion.dial_features import FEATURE_LABELS, FEATURE_MAXIMA, PLOT_FEATURES
from app.repositories.learner_repository import LearnerRepository
from app.repositories.learner_sitting_repository import LearnerSittingRepository
from app.schemas.dto import DialMetric, LearnerOverview, SittingPoint


class LearnerNotFoundError(Exception):
    """No such learner on the caseload. The router reports this as a 404."""


class LearnerOverviewService:
    def __init__(self):
        self.learners = LearnerRepository()
        self.sittings = LearnerSittingRepository()

    def get_overview(self, learner_id: str) -> LearnerOverview:
        learner = self.learners.find_by_id(learner_id)
        if not learner:
            raise LearnerNotFoundError(f"No learner {learner_id}.")

        # Oldest first — the order the chart plots left to right. The repository owns that
        # rule so the frontend never has to sort semester strings itself.
        history = self.sittings.list_by_learner(learner_id)

        return LearnerOverview(
            learner_id=str(learner.get("id", learner_id)),
            pseudonym=learner.get("pseudonym") or "",
            tier=learner.get("tier") or "",
            on_caseload=bool(learner.get("on_caseload")),
            # The current marks live on the learner row itself — same dict, no second read.
            metrics=self._metrics(learner),
            history=[SittingPoint(**{k: row.get(k) for k in SittingPoint.model_fields})
                     for row in history],
            student_id=learner.get("student_id"),
            semester=learner.get("semester"),
            band=learner.get("band"),
            band_group=learner.get("band_group"),
            cluster_band=learner.get("cluster_band"),
            cluster_cohort=learner.get("cluster_cohort"),
        )

    # ── helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _metrics(scores: dict | None) -> list[DialMetric]:
        """The four DIAL marks as radar-ready metrics.

        Always returns all four, even when none was assessed: the chart names what it omitted
        ("Writing not assessed"), which it cannot do from a list that silently drops it.

        `assessed` is False whenever the mark is missing — writing for every band A learner, and
        every mark for a learner created in the app rather than loaded from the workbook — and
        the chart drops that axis rather than drawing a zero, which would claim the learner
        scored nothing on a paper they never sat.
        """
        if not scores:
            return []

        metrics = []
        for key in PLOT_FEATURES:
            raw = scores.get(key)
            metrics.append(DialMetric(
                key=key,
                label=FEATURE_LABELS[key],
                raw=None if raw is None else float(raw),
                max=FEATURE_MAXIMA[key],
                # Null percentile with a present mark means the ingest predates the percentile
                # columns; the mark still shows in the legend, it just cannot be plotted.
                percentile=(
                    None if scores.get(f"{key}_pct") is None else float(scores[f"{key}_pct"])
                ),
                assessed=raw is not None and scores.get(f"{key}_pct") is not None,
            ))
        return metrics
