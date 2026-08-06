"""ProfilingService - Subsystem 2 orchestration.

Promotes a learner's most recent sitting onto their `learners` row, so the dashboard, the radar
chart and activity generation all read one agreed set of current marks.

THERE IS NO ALGORITHM HERE ANY MORE. `generate_profile` used to run ProfilingAlgorithm.analyse()
over `assessment_records`, deriving seven cognitive dimensions by keyword-matching subtest names.
Those dimensions were mock scaffolding; the system standardises on the four marks DAS actually
measures. A profile is therefore something a learner HAS, not something we compute — and
"generate" means "take the newest scores on record and make them current".

WHY THE PROMOTION STEP EXISTS AT ALL, given the ingest already writes the newest sitting to
`learners`: the ingest is offline and runs over the workbook. UC1's upload path appends a
sitting at any time, and this is what pulls that sitting through to every read that matters.
The two writers converge on `learner_sittings`, and this is the one place that reads from it.

    no sittings at all -> NoScoresError  (the router's 409; the page offers the upload flow)
    the write fails    -> StorageError   (the router's 500 — infrastructure, not the learner)

StorageError is deliberately not caught: it means the database is unreachable, which is a
different problem from the learner having no scores, and the therapist can act on only one of
them.
"""
from app.repositories.learner_repository import LearnerRepository
from app.repositories.learner_sitting_repository import LearnerSittingRepository

# Copied from the newest sitting onto the learner. Exactly the columns the radar chart, the
# cohort scatter and ActivityGenerationService read — `semester`, `band` and `band_group` ride
# along because a learner's band changes between sittings and the marks are meaningless without
# the paper they were scored against.
PROMOTED = (
    "semester", "band", "band_group",
    "phonics", "word_reading_accuracy", "word_spelling", "writing", "writing_genre",
    "phonics_pct", "word_reading_accuracy_pct", "word_spelling_pct", "writing_pct",
)


class NoScoresError(Exception):
    """The learner has no sittings, so there are no scores to make current.

    NOT a failure of profiling — it is the ordinary state of a learner who has never been
    assessed, and the only thing the therapist can do about it is upload an assessment. The
    router turns this into a 409 and the profile page turns that into the upload prompt, which
    is why it is its own type rather than a bare 404.
    """


class ProfilingService:
    def __init__(self):
        self.learners = LearnerRepository()
        self.sittings = LearnerSittingRepository()

    def generate_profile(self, learner_id: str) -> dict:
        """Make the learner's most recent sitting their current marks.

        Idempotent: running it twice with no new sitting writes the same values again. That is
        deliberate — the button is safe to press, and pressing it is how a therapist pulls
        through an assessment someone else just uploaded.
        """
        latest = self.sittings.latest_for_learner(learner_id)
        if not latest:
            raise NoScoresError(
                f"No assessment scores on record for learner {learner_id}."
            )

        # Only the promoted columns, never the sitting's own `id` or `learner_id` — writing
        # either would overwrite the learner's identity with the sitting's.
        promoted = {key: latest.get(key) for key in PROMOTED}
        self.learners.save({**promoted, "id": learner_id})

        # `learner_id`, NOT the `id` the write used. The row being updated is the learner, so
        # `id` is right for the upsert — but a caller asking "whose profile is this?" means the
        # learner, and the endpoint's contract has always answered with `learner_id`.
        return {
            "learner_id": learner_id,
            **promoted,
            "source": latest.get("source"),
            "sitting_id": latest.get("id"),
        }

    def list_sittings(self, learner_id: str) -> list[dict]:
        """The learner's whole score history, oldest first — the line chart's series."""
        return self.sittings.list_by_learner(learner_id)
