"""Request/response DTOs for the API layer."""
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, field_validator
from app.ingestion.dial_features import FEATURE_LABELS, NORMALISATION_CEILINGS
from app.ingestion.semesters import SEMESTER_RE

MetricType = Literal["writing", "phonics", "word_reading", "word_spelling"]

class Credentials(BaseModel):
    email: EmailStr
    password: str


class SignUpResult(BaseModel):
    """Response for POST /auth/signup.

    When Supabase email confirmation is enabled, `session` is None and
    `email_confirmation_required` is True: the user must click the emailed link
    before they can log in.
    """
    user_id: Optional[str] = None
    email: EmailStr
    email_confirmation_required: bool = False
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class Session(BaseModel):
    """Response for POST /auth/login: a live Supabase session."""
    user_id: str
    email: EmailStr
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: Optional[int] = None


class GenerationParams(BaseModel):
    """Body of POST /activities/{learner_id}/generate.

    Every field is optional: with an empty body the service derives the retrieval
    query from the learner's profile alone. concept/stage are curriculum metadata
    filters applied inside the match RPC, mirroring the CLI's flags.

    BAND IS NOT ONE OF THEM. Retrieval is scoped to the learner's own band_group,
    read server-side, so a learner can never be grounded in another band's
    curriculum — a caller-supplied band would be a way around exactly that.
    """
    literacy_objective: str = ""
    level: str = ""
    band: Optional[str] = None   # accepted for back-compat; IGNORED for retrieval scope
    concept: Optional[str] = None
    stage: Optional[str] = None
    notes: str = ""           # free-text steer, appended to the profile-derived query
    k: int = 3                # grounding chunks to retrieve
    extra: dict = {}


class ReviewIn(BaseModel):
    activity_id: str
    text: str
    approval_status: Literal["APPROVED", "REJECTED"] | None = None

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Review text must not be empty")
        return value


class ShareIn(BaseModel):
    activity_id: str
    recipient_email: str

class SubtestResult(BaseModel):
    name: str
    standard_score: int
    percentile: int


class TaskResult(BaseModel):
    name: str
    score: int
    max_score: int


class AssessmentPreview(BaseModel):
    """Returned by POST /assessments/preview. The frontend renders this as a review card; the
    therapist confirms before anything is saved.

    The four DIAL marks are None here, always: the parser does not read them out of the report
    (see assessment_parser). They exist on this model so the preview and the confirm request have
    one shape, and the therapist types them in.
    """
    learner_id: str
    assessment_date: str
    tasks: list[TaskResult] = []
    strengths: list[str] = []
    weaknesses: list[str] = []
    confidence_score: float = 0.0
    risk_score: float = 0.0
    task_results: dict = {}
    notes: str = ""
    writing_score: float | None = None
    phonics_score: float | None = None
    word_reading_score: float | None = None
    word_spelling_score: float | None = None


# Request field -> the DIAL feature (and therefore the learner_sittings column) it carries.
# Note `word_reading_score` -> `word_reading_accuracy`: the names differ, so anything mapping
# between the upload payload and a sitting row must go through here rather than guess.
_METRIC_TO_FEATURE = {
    "writing_score": "writing",
    "phonics_score": "phonics",
    "word_reading_score": "word_reading_accuracy",
    "word_spelling_score": "word_spelling",
}


class AssessmentConfirmRequest(BaseModel):
    learner_id: str
    assessment_date: str
    risk_score: float
    task_results: dict
    strengths: list[str] = []
    weaknesses: list[str] = []
    confidence_score: float = 0.0
    # The semester this assessment belongs to, e.g. '2026 Sem 1'. REQUIRED, because it is half of
    # `learner_sittings`' natural key (learner_id, semester) and the sort key that decides which
    # sitting is "latest" — there is no sensible default, and a wrong one silently misfiles the
    # marks. Validated by shape rather than against the list of semesters already on record, so
    # the first upload of a new semester is never blocked.
    semester: str
    # The paper these marks were earned against. Carried on the sitting because the rubric moves
    # between bands — phonics is out of 30 in A2 and 46 in A3 — so a mark without its band cannot
    # be compared with anything. `band_group` is also what scopes UC3's retrieval and what
    # percentiles rank within, so a sitting without one is much less useful than it looks.
    band: str | None = None
    band_group: str | None = None
    writing_score: float | None = None
    phonics_score: float | None = None
    word_reading_score: float | None = None
    word_spelling_score: float | None = None

    @field_validator("semester")
    @classmethod
    def semester_is_well_formed(cls, value: str) -> str:
        """'<year> Sem <1|2>' — the shape every ordering in the system depends on.

        `learner_sittings.semester` is plain text with no database constraint, and both
        `latest_for_learner` and the workbook's reduction sort it AS TEXT ('2022 Sem 2' <
        '2023 Sem 1'). That only holds while the shape is exact: '2026 Sem 10' or 'Sem 1 2026'
        would sort somewhere arbitrary, so the sitting would either never be found as the latest
        or wrongly be. Nothing downstream would error — it would just be quietly wrong, which is
        why this is rejected at the boundary.
        """
        value = value.strip()
        if not SEMESTER_RE.fullmatch(value):
            raise ValueError(
                f"semester must look like '2026 Sem 1' (got {value!r})"
            )
        return value

    @field_validator(
        "writing_score", "phonics_score", "word_reading_score", "word_spelling_score"
    )
    @classmethod
    def score_within_rubric(cls, value: float | None, info) -> float | None:
        """0 <= score <= ceiling, matching the frontend's displayed valid range.

        NOT ASSESSED IS NOT ZERO, so None passes straight through. Writing is never administered
        to band A at all, and a 0 there would be a real mark of zero: it would rank as the
        learner's weakest skill, drive the retrieval query, and produce a writing activity for a
        learner who has never sat the paper. `normalised_score` returns None for None, and the
        radar omits the axis rather than plotting it at the origin.
        """
        if value is None:
            return None
        max_score = NORMALISATION_CEILINGS[_METRIC_TO_FEATURE[info.field_name]]
        if not (0 <= value <= max_score):
            raise ValueError(
                f"{info.field_name} must be between 0 and {max_score:g} "
                f"(got {value:g})"
            )
        return value


class AssessmentMetric(BaseModel):
    """One row of the upload form's score entry, served by GET /assessments/metrics.

    SERVED RATHER THAN HARDCODED IN THE UI, for the same reason `DialMetric.max` is: a second copy
    of the rubric in the frontend is a second thing to get wrong when a paper changes, and this
    one has to agree with the confirm validator exactly or the form accepts marks the API rejects.

    `max` is the NORMALISATION ceiling (phonics 50, writing 30), not the exact rubric maximum
    (46, 24) that DialMetric.max carries. The two are deliberately different numbers — see
    dial_features — and this is the one the validator enforces.
    """
    key: str            # the confirm-request field name, e.g. 'phonics_score'
    label: str          # 'Phonics'
    max: float          # inclusive upper bound the form should enforce


def assessment_metrics() -> list[AssessmentMetric]:
    """The four metrics in the order the form should offer them."""
    return [
        AssessmentMetric(
            key=key,
            label=FEATURE_LABELS[feature],
            max=NORMALISATION_CEILINGS[feature],
        )
        for key, feature in _METRIC_TO_FEATURE.items()
    ]


# ── Cohort clustering — GET /dashboard/clusters (UC2) ────────────────────────
class CohortLearner(BaseModel):
    """One point in the dashboard's 3D scatter.

    Scores are the RAW marks, not normalised to a percentage: phonics is out of 46 while word
    reading is out of 10, and a therapist reading the cluster table wants the mark that was
    actually awarded. Graph.jsx sets each axis range from PLOT_SKILLS[...].max instead.

    Any score may be null — `writing` is absent for band A entirely — and the frontend drops a
    point from the plot when the axis it needs is missing.
    """
    id: str                          # learners.id — a uuid, and ALWAYS present
    # The anonymised workbook id, e.g. 'Student 0001'. Null for a learner created in the app.
    student_id: Optional[str] = None
    # Empty for cohort rows — the research cohort has no names. The table falls back to
    # student_id, which is the only identity those learners have.
    pseudonym: str = ""
    # Whether this is one of the therapist's own learners. Only they carry assessment records,
    # so only they can be profiled. Informational only — every learner can now be profiled.
    on_caseload: bool = False
    band: Optional[str] = None       # fine band, A1..C9
    band_group: Optional[str] = None

    # BOTH clustering scopes travel together and the dashboard picks one — the toggle must not
    # need a round trip, and the two are the same 5,783 rows read once.
    #   cluster_band    '<band_group> <rank>', e.g. 'B 2' — one k-means model per band group
    #   cluster_cohort  'Cohort <rank>'                   — one model over the whole cohort
    # Either may be null, and for different reasons: a learner with no band group gets no
    # cluster_band, while cluster_cohort is set for everyone with the three core scores.
    cluster_band: Optional[str] = None
    cluster_cohort: Optional[str] = None
    writing_genre: Optional[str] = None

    phonics: Optional[float] = None
    word_reading_accuracy: Optional[float] = None
    word_spelling: Optional[float] = None
    writing: Optional[float] = None


class ClusteringRunOut(BaseModel):
    """How k was chosen for one model — the evidence behind the colours.

    `silhouette_by_k` is the whole k = 2..10 sweep, so the UI can show that k was selected
    rather than configured, and compare the two scopes on the same measure.
    """
    scope: str                       # 'cohort' | 'band'
    tier: str                        # 'Cohort', or the band group ('A' | 'B' | 'C')
    features: list[str] = []
    k: int
    best_silhouette: float
    silhouette_by_k: dict[str, float] = {}
    n_learners: int


class CohortClusters(BaseModel):
    """Response of GET /dashboard/clusters — the whole cohort in one call.

    One request by design: the previous Graph.jsx fanned out to one /learners/{id}/profiles per
    learner, which at cohort scale would be 5,784 requests. Both clustering scopes ride along
    for the same reason — flipping the dashboard's toggle should not cost a round trip.
    """
    learners: list[CohortLearner] = []
    runs: list[ClusteringRunOut] = []
    # Keyed by scope, because the answer differs between them: every learner has a cohort
    # label, but those with no band group have no band label. One number would be wrong for
    # one of the two views.
    unclustered: dict[str, int] = {}


# ── Merged learner view — GET /learners/{id}/overview (UC2) ──────────────────
class DialMetric(BaseModel):
    """One DIAL assessment mark, in the two forms the profile page needs at once.

    `raw` out of `max` is the mark the therapist reads and the number that goes in the legend.
    `percentile` is what the radar chart's radius can actually carry: the four marks are scored
    on different rubrics (phonics /46, word reading /10) AND the rubric differs by band — phonics
    tops out at 25 in A1 and 46 in A3 — so neither the raw mark nor percent-of-max is comparable
    across the axes of one chart. The percentile ranks the learner within their own band group;
    see infra/migrations/2026-08-06_score_percentiles.sql.

    `assessed` is NOT `raw is not None` restated for convenience — it is the distinction the
    chart turns on. Writing is never administered to band A, so 2,084 learners have no writing
    mark, and drawing them at zero would assert they scored nothing on a paper they never sat.
    The radar drops an unassessed axis instead of plotting it.
    """
    key: str                            # a PLOT_SKILLS key, e.g. 'phonics'
    label: str
    raw: Optional[float] = None
    max: float                          # top of the rubric — served so the UI keeps no second copy
    percentile: Optional[float] = None  # 0-100, within band_group
    assessed: bool = False


class SittingPoint(BaseModel):
    """One learner's marks in one semester — a point on the profile page's line chart.

    Carries the RAW marks and their percentiles side by side because the chart's scale toggle
    switches between them: the four rubrics are not comparable to each other (phonics /46, word
    reading /10), so plotting them together needs percentiles, while reading one metric on its
    own wants the mark that was actually awarded.

    `band` belongs to the SITTING, not the learner. Phonics is out of 30 in band A2 and 46 in
    A3, so a learner who moves band mid-history has marks that are not on one scale — which is
    the deeper reason the percentile view exists.
    """
    semester: str
    band: Optional[str] = None
    band_group: Optional[str] = None
    source: str = "workbook"            # 'workbook' (ingest) | 'upload' (UC1) | 'seed'

    phonics: Optional[float] = None
    word_reading_accuracy: Optional[float] = None
    word_spelling: Optional[float] = None
    writing: Optional[float] = None

    phonics_pct: Optional[float] = None
    word_reading_accuracy_pct: Optional[float] = None
    word_spelling_pct: Optional[float] = None
    writing_pct: Optional[float] = None


class LearnerOverview(BaseModel):
    """Everything LearnerDetailPage needs about one learner, in one call.

    Three things, from two tables:

      identity + current marks   the `learners` row — what the header and radar chart read
      history                    `learner_sittings`, oldest first — the line chart's series

    NOTHING IS REQUIRED EXCEPT IDENTITY, and the gaps are ordinary rather than error states:
      metrics all unassessed   the learner has no marks yet (created in the app, never in the
                               DIAL workbook) — the page offers the upload flow instead
      history empty            same cause; a learner with exactly ONE sitting is also normal,
                               and renders as a single point rather than a line
    Only an unknown learner raises.
    """
    learner_id: str
    pseudonym: str = ""
    tier: str = ""
    # Whether this is one of the therapist's own learners. INFORMATIONAL — it drives the
    # "Caseload" badge, not what the page lets you do. Every learner can be profiled, have an
    # activity generated and be shared, because a profile is now just their marks.
    on_caseload: bool = False

    # The DIAL side, straight off the learner row: their CURRENT marks.
    metrics: list[DialMetric] = []

    # Every sitting on record, oldest first. Rides along rather than sitting behind its own
    # endpoint because the page always wants both, and at most ten rows is nothing on the wire.
    history: list[SittingPoint] = []
    student_id: Optional[str] = None    # anonymised workbook id, null for app-created learners
    semester: Optional[str] = None      # which sitting the marks come from
    band: Optional[str] = None          # fine band, A1..C9
    band_group: Optional[str] = None    # the population `percentile` is ranked against
    cluster_band: Optional[str] = None
    cluster_cohort: Optional[str] = None


# ── Learner list — GET /learners (UC2) ───────────────────────────────────────
class LearnerListItem(BaseModel):
    """One card in the Learners tab.

    Deliberately thin. The list can span the whole table, so every field here is multiplied by
    the page size on the wire and by the row count in the count query — the detail page fetches
    the rest when a card is actually opened.
    """
    id: str
    student_id: Optional[str] = None
    # Empty for cohort rows; the card falls back to student_id, their only identity.
    pseudonym: str = ""
    tier: str = ""
    on_caseload: bool = False
    band: Optional[str] = None
    band_group: Optional[str] = None
    cluster_cohort: Optional[str] = None


class LearnerPage(BaseModel):
    """Response of GET /learners — one page, plus enough to render a pager.

    PAGED BECAUSE THE TABLE IS LARGE. Since the 2026-08-07 merge `learners` holds the whole DAS
    cohort as well as the caseload, and PostgREST caps a select at 1,000 rows and truncates
    WITHOUT erroring — the old bare-array response would have silently served a sixth of the
    table while looking perfectly healthy.

    `total` counts everything matching the CURRENT filters, not the table, so the pager can say
    "1-24 of 137" for a search as readily as "1-24 of 5,783" for the default view.
    """
    items: list[LearnerListItem] = []
    total: int = 0
    page: int = 1
    per_page: int = 24
