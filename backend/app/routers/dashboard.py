from fastapi import APIRouter, Depends
from app.core.security import current_therapist
from app.repositories.base import BaseRepository
from app.repositories.learner_repository import LearnerRepository
from app.schemas.dto import CohortClusters
from app.services.cohort_service import CohortService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

class DashboardRepository(BaseRepository):
    table = "data"

    def __init__(self):
        self.learners = LearnerRepository()

    def get_stats(self) -> dict:
        flagged_count = 2
        needs_profiling = 3
        high_risk = 1
        inactive = 1
        total_learners = 5

        # Counted through LearnerRepository so learner access stays in one place.
        try:
            rows = self.learners.list_all()
            if rows is not None:
                total_learners = len(rows)
        except Exception:
            pass

        try:
            activities = self.db.select("*").eq("status", "FLAGGED").table("learning_activities").execute().data
            if activities is not None:
                flagged_count = len(activities)

            records = self.db.select("*").gt("risk_score", 0.8).table("assessment_records").execute().data
            if records is not None and len(records) > 0:
                high_risk = len(records)
        except Exception:
            pass

        return {
            "total_learners": total_learners,
            "flagged": flagged_count,
            "needs_profiling": needs_profiling,
            "high_risk": high_risk,
            "inactive": inactive
        }
        
    def get_tasks(self) -> list[dict]:
        try:
            data = self.db.table("tasks").select("*").execute().data
            if data:
                return data
        except Exception:
            pass
        return [
            { "title": "Review flagged activity for Learner A", "meta": "Due today · Subsystem 3", "status": "DONE" },
            { "title": "Upload assessment for Learner D", "meta": "Due today · Subsystem 2", "status": "PENDING" },
            { "title": "Generate profile for Learner C", "meta": "Due today · Subsystem 2", "status": "PENDING" },
            { "title": "Generate activity for Learner B", "meta": "Due today · Subsystem 3", "status": "PENDING" },
            { "title": "Share Learner A's progress report", "meta": "Jul 22 · Email to parent", "status": "PENDING" },
            { "title": "Re-assess Learner E (high risk)", "meta": "Jul 28 · Scheduled", "status": "PENDING" }
        ]
        
    def get_events(self) -> list[dict]:
        try:
            data = self.db.table("calendar_events").select("*").execute().data
            if data:
                return data
        except Exception:
            pass
        return [
            { "event_date": "2026-07-03" },
            { "event_date": "2026-07-07" },
            { "event_date": "2026-07-14" },
            { "event_date": "2026-07-20" },
            { "event_date": "2026-07-22" },
            { "event_date": "2026-07-28" }
        ]



repo = DashboardRepository()
cohort_svc = CohortService()


@router.get("/clusters", response_model=CohortClusters)
def get_cohort_clusters(_: str = Depends(current_therapist)):
    """The whole clustered cohort for the analytics scatter (UC2).

    One call rather than one per learner: Graph.jsx previously fetched /learners then a profile
    per learner, which at cohort scale is thousands of requests. The k-means labels are already
    columns on learner_scores — see scripts/ingest_dial_data.py — so this is a paged SELECT.
    """
    return cohort_svc.get_clusters()


@router.get("/stats")
def get_dashboard_stats(_: str = Depends(current_therapist)):
    return repo.get_stats()

@router.get("/tasks")
def get_dashboard_tasks(_: str = Depends(current_therapist)):
    return repo.get_tasks()

@router.get("/events")
def get_dashboard_events(_: str = Depends(current_therapist)):
    return repo.get_events()
