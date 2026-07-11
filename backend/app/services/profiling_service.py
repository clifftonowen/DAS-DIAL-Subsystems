"""ProfilingService - Subsystem 2 orchestration.

Pulls a learner's assessment records, runs the ProfilingAlgorithm, stores
and returns the LearnerProfile.
"""
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.learner_profile_repository import LearnerProfileRepository
from app.agents.profiling_algorithm import ProfilingAlgorithm


class ProfilingService:
    def __init__(self):
        self.assessments = AssessmentRepository()
        self.profiles = LearnerProfileRepository()
        self.algorithm = ProfilingAlgorithm()

    def generate_profile(self, learner_id: str) -> dict:
        records = self.assessments.find_by_learner(learner_id)
        metrics = self.algorithm.analyse(records)
        profile = {"learner_id": learner_id, **metrics}
        self.profiles.save(profile)
        return profile
