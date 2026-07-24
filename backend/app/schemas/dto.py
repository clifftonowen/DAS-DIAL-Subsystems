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
    literacy_objective: str = ""
    level: str = ""
    extra: dict = {}


class ReviewIn(BaseModel):
    activity_id: str
    text: str


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