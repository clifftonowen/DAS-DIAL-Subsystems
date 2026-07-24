"""ActivityGenerationService - Subsystem 3 orchestration.

Builds a prompt from the learner profile + retrieved strategies, runs the
ActivityGraph, persists the resulting LearningActivity.
"""
from app.repositories.learner_profile_repository import LearnerProfileRepository
from app.repositories.activity_repository import ActivityRepository
from app.services.retrieval_service import RetrievalService
from app.agents.activity_graph import ActivityGraph


class ActivityGenerationService:
    def __init__(self):
        self.profiles = LearnerProfileRepository()
        self.activities = ActivityRepository()
        self.retrieval = RetrievalService()
        self.graph = ActivityGraph()

    def build_prompt(self, profile: dict, strategies: list[dict], params: dict) -> str:
        return (
            f"Generate a literacy activity.\nProfile: {profile}\n"
            f"Grounding strategies: {strategies}\nParams: {params}"
        )

    def generate(self, profile_id: str, params: dict) -> dict:
        profile = self.profiles.find_by_learner(profile_id) or {"learner_id": profile_id}
        strategies = self.retrieval.retrieve_strategies(profile)
        prompt = self.build_prompt(profile, strategies, params)
        activity = self.graph.run(prompt)
        activity["profiled"] = profile_id
        self.activities.save(activity)
        return activity

    def list_activities(self, profile_id: str) -> list[dict]:
        return self.activities.find_by_profile(profile_id)
