"""Domain models (Entity layer of the class diagram).

Plain dataclasses / pydantic models — no persistence logic here.
"""
from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


class ActivityStatus(str, Enum):
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    FLAGGED = "FLAGGED"


class Therapist(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    email: str
    auth_user_id: UUID | None = None
    name: str = ""


class Learner(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pseudonym: str
    band_level: str          # Band A / B / C
    tier: str = ""


class AssessmentRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    learner_id: UUID
    assessment_date: date | None = None
    risk_score: float = 0.0
    task_results: dict = {}
    strengths: list[str] = []
    weaknesses: list[str] = []
    confidence_score: float = 0.0


class LearnerProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    learner_id: UUID
    phonological_processing: float = 0.0
    decoding: float = 0.0
    spelling: float = 0.0
    comprehension: float = 0.0
    working_memory: float = 0.0
    executive_functioning: float = 0.0
    visualisation: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InstructionalStrategy(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    content: str
    source: str = ""
    tags: list[str] = []


class LearningActivity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    activity_id: UUID | None = None
    learner_id: UUID | None = None        # who the activity was generated for
    content: dict = {}
    literacy_objective: str = ""
    level: str = ""
    status: ActivityStatus = ActivityStatus.GENERATED
    grounded_on: list[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Review(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    activity_id: UUID
    therapist_id: UUID
    text: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
