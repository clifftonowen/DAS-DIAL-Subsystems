"""Request/response DTOs for the API layer."""
from pydantic import BaseModel


class Credentials(BaseModel):
    email: str
    password: str


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
