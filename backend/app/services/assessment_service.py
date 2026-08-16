"""AssessmentService — parse an uploaded assessment report into a preview, then persist it
once the therapist confirms.

TWO TABLES, ONE CONFIRM. `assessment_records` keeps the uploaded report as submitted — the task
rows, the risk and confidence scores, the strengths and weaknesses. `learner_sittings` keeps the
four DIAL marks as a dated sitting, which is the grain the rest of the system reads: the profile
page's line chart, and the row ProfilingService promotes when a therapist clicks Generate Profile.

Writing only the first was the gap this module used to have. `learner_sitting_repository` has
always named UC1's upload as one of the table's three writers, but nothing implemented it — so a
therapist could upload an assessment, click Generate Profile, and be told the learner had no
scores on record. The upload reached the database and never reached the learner.
"""
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.learner_repository import LearnerRepository
from app.repositories.learner_sitting_repository import LearnerSittingRepository
from app.entities.models import AssessmentRecord
from app.ingestion.assessment_parser import parse_assessment_report, validate_format
from app.ingestion.dial_features import PLOT_FEATURES
from app.ingestion.semesters import option_list
from app.schemas.dto import (
    AssessmentPreview, AssessmentConfirmRequest, _METRIC_TO_FEATURE,
)
from app.services.percentiles import percentile_of


class StorageError(Exception):
    pass


class AssessmentService:
    def __init__(self):
        self.assessments = AssessmentRepository()
        self.sittings = LearnerSittingRepository()
        self.learners = LearnerRepository()

    def parse_preview(self, learner_id: str, file) -> AssessmentPreview:
        validate_format(file)
        return parse_assessment_report(file, learner_id)

    def list_semesters(self) -> list[str]:
        """Semesters the upload form offers — those on record plus the next two.

        NOTHING CATCHES ABOVE THIS. It is one half of UploadView's `Promise.all`, so an exception
        here does not degrade the form, it kills it: the rejection leaves `metricSpecs` empty and
        `handleSubmit` bails on its `!semester` guard. That is why the repository falls back to a
        paged scan when the `distinct_semesters()` function is absent rather than propagating.
        """
        return option_list(self.sittings.distinct_semesters())

    def confirm_and_save(self, payload: AssessmentConfirmRequest) -> dict:
        """Persist the confirmed assessment as a sitting AND an assessment record.

        THE SITTING IS WRITTEN FIRST, DELIBERATELY. PostgREST gives no cross-table transaction, so
        one write can succeed while the other fails, and the order decides what a retry does.
        Sitting first means a retry re-upserts the same (learner_id, semester) row — harmless.
        Record first would mean a retry appends a SECOND assessment record, because
        `AssessmentRecord.id` is a fresh uuid on every call and the repository upserts on it.
        """
        sitting = self._build_sitting(payload)
        try:
            self.sittings.upsert_many([sitting])
        except Exception as e:
            raise StorageError(str(e))

        record = AssessmentRecord(
            learner_id=payload.learner_id,
            assessment_date=payload.assessment_date,
            risk_score=payload.risk_score,
            task_results=payload.task_results,
            strengths=payload.strengths,
            weaknesses=payload.weaknesses,
            confidence_score=payload.confidence_score,
            writing_score=payload.writing_score,
            phonics_score=payload.phonics_score,
            word_reading_score=payload.word_reading_score,
            word_spelling_score=payload.word_spelling_score,
        )
        try:
            saved = self.assessments.save(record.model_dump(mode="json"))
        except Exception as e:
            raise StorageError(str(e))
        return {
            "status": "success",
            "message": "Data saved successfully",
            "record": saved,
            "sitting": sitting,
        }

    def list_assessments(self, learner_id: str) -> list[dict]:
        return self.assessments.find_by_learner(learner_id)

    # ── helpers ───────────────────────────────────────────────────────────
    def _build_sitting(self, payload: AssessmentConfirmRequest) -> dict:
        """The `learner_sittings` row this upload becomes.

        Shaped like `scripts.ingest_dial_data.build_sitting_rows`, the table's other writer: no
        `id` (Postgres generates it, and the upsert conflicts on the natural key), `source` named
        explicitly, and a missing mark stored as None rather than 0.

        `band`/`band_group` come off the PAYLOAD, falling back to the learner's current values.
        The band belongs on the sitting because the rubric moves between bands — phonics is out
        of 30 in A2 and 46 in A3 — so a mark recorded without the paper it was earned against
        cannot honestly be compared with anything later.
        """
        marks = {
            feature: getattr(payload, field)
            for field, feature in _METRIC_TO_FEATURE.items()
        }

        band, band_group = payload.band, payload.band_group
        if band is None or band_group is None:
            learner = self.learners.find_by_id(payload.learner_id) or {}
            band = band if band is not None else learner.get("band")
            band_group = band_group if band_group is not None else learner.get("band_group")

        return {
            "learner_id": payload.learner_id,
            "semester": payload.semester,
            "band": band,
            "band_group": band_group,
            "source": "upload",
            **marks,
            **self._percentiles(marks, payload.semester, band_group),
        }

    def _percentiles(self, marks: dict, semester: str, band_group: str | None) -> dict:
        """`<feature>_pct` for each mark, ranked within (semester, band_group).

        WITHOUT THIS THE UPLOAD MAKES THE PROFILE PAGE WORSE. `LearnerOverviewService` treats a
        metric as assessed only when it has BOTH a mark and a percentile, so a sitting with null
        percentiles renders every radar axis as "not assessed" — and since ProfilingService
        promotes all twelve columns, it would also overwrite percentiles the workbook had already
        computed for that learner.

        All None when the learner has no band group: there is no population to rank against, and
        ranking them against another band's paper is the exact comparison percentiles exist to
        prevent.
        """
        keys = [f"{feature}_pct" for feature in PLOT_FEATURES]
        if not band_group:
            return dict.fromkeys(keys)

        peers = self.sittings.peer_marks(semester, band_group)
        return {
            f"{feature}_pct": percentile_of(
                marks.get(feature),
                # The learner's own mark has to be IN the population it is ranked against — the
                # workbook ranks every row within its group, self included. This upload's row is
                # not stored yet, so it is appended here.
                [peer.get(feature) for peer in peers] + [marks.get(feature)],
            )
            for feature in PLOT_FEATURES
        }
