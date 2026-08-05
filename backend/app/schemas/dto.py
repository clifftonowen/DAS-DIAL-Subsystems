"""Request/response DTOs for the API layer."""
from typing import Optional
from pydantic import BaseModel, EmailStr


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
    """Body of POST /activities/{profile_id}/generate.

    Every field is optional: with an empty body the service derives the retrieval
    query from the learner's profile alone. band/concept/stage are the curriculum
    metadata filters applied inside the match RPC, mirroring the CLI's flags.
    """
    literacy_objective: str = ""
    level: str = ""
    band: Optional[str] = None
    concept: Optional[str] = None
    stage: Optional[str] = None
    notes: str = ""           # free-text steer, appended to the profile-derived query
    k: int = 3                # grounding chunks to retrieve
    extra: dict = {}


class ReviewIn(BaseModel):
    activity_id: str
    text: str
    status: str | None = None


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
    """Returned by POST /assessments/preview. The frontend renders this as
    a review card; the therapist confirms before anything is saved."""
    learner_id: str
    assessment_date: str
    tasks: list[TaskResult] = []
    strengths: list[str] = []
    weaknesses: list[str] = []
    confidence_score: float = 0.0
    risk_score: float = 0.0
    task_results: dict = {}
    notes: str = ""


class AssessmentConfirmRequest(BaseModel):
    learner_id: str
    assessment_date: str
    risk_score: float
    task_results: dict
    strengths: list[str] = []
    weaknesses: list[str] = []
    confidence_score: float = 0.0


# ── Cohort clustering — GET /dashboard/clusters (UC2) ────────────────────────
class CohortLearner(BaseModel):
    """One point in the dashboard's 3D scatter.

    Scores are the RAW marks, not normalised to a percentage: phonics is out of 46 while word
    reading is out of 10, and a therapist reading the cluster table wants the mark that was
    actually awarded. Graph.jsx sets each axis range from PLOT_SKILLS[...].max instead.

    Any score may be null — `writing` is absent for band A entirely — and the frontend drops a
    point from the plot when the axis it needs is missing.
    """
    id: str                          # anonymised student id, e.g. 'Student 0001'
    band: Optional[str] = None       # fine band, A1..C9
    band_group: Optional[str] = None
    # Set only where a cohort student is also on the therapist's caseload. The cluster table
    # links the name to LearnerDetailPage only when this is present, because GET /learners/{id}
    # would 404 for a cohort-only student.
    learner_id: Optional[str] = None

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