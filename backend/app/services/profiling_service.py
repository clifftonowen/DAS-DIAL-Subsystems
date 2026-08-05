"""ProfilingService - Subsystem 2 orchestration.

Pulls a learner's assessment records, runs the ProfilingAlgorithm, stores
and returns the LearnerProfile.

This is the `ProfilingService` lifeline of the UC2 sequence diagram, and its failure
branches are the `alt` blocks there:

    no records found          -> EmptyDataError          (flow 2a, UT-2.4, ST-2.2)
    no valid patterns         -> ProfileGenerationError  (flow 4a, UT-2.5, ST-2.3)
    database refuses the save -> StorageError            (flow 6a, UT-2.11, ST-2.4)

StorageError is deliberately NOT caught here. It means the database is unreachable, which is
an infrastructure fault the router reports as a 500 — quite different from the two above,
which are statements about the learner's data that the therapist can act on.
"""
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.learner_profile_repository import LearnerProfileRepository
from app.agents.profiling_algorithm import NoPatternError, ProfilingAlgorithm


class EmptyDataError(Exception):
    """The learner has no assessment records, so there is nothing to profile.

    Distinct from NoPatternError: this learner has never been assessed (the therapist needs
    to upload an assessment), whereas NoPatternError means records exist but evidenced
    nothing (the records, or our parsing of them, are the problem). The two lead to
    different messages and different next actions, so they are different types.
    """


class ProfileGenerationError(Exception):
    """Records existed but no profile could be built from them."""


class ProfilingService:
    def __init__(self):
        self.assessments = AssessmentRepository()
        self.profiles = LearnerProfileRepository()
        self.algorithm = ProfilingAlgorithm()

    def generate_profile(self, learner_id: str) -> dict:
        records = self.assessments.find_by_learner(learner_id)
        if not records:
            raise EmptyDataError(f"No assessment records for learner {learner_id}.")

        try:
            metrics = self.algorithm.analyse(records)
        except NoPatternError as exc:
            # Translated at the layer boundary: the router should not need to know the
            # algorithm exists, only that profile generation failed and why.
            raise ProfileGenerationError(str(exc)) from exc

        profile = {"learner_id": learner_id, **metrics}
        self.profiles.save(profile)
        return profile

    def list_profiles(self, learner_id: str) -> list[dict]:
        return self.profiles.list_by_learner(learner_id)
