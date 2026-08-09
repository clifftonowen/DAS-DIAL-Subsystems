"""LearnerService — the Learners tab's read side.

`learners` holds both the therapist's caseload and the ~5,783-row anonymised research cohort
(see infra/migrations/2026-08-07_merge_learner_scores.sql), so listing is PAGED and SEARCHED
SERVER-SIDE. The page used to fetch every learner and filter in the browser; at cohort scale
that is both a truncated read — PostgREST caps a select at 1,000 rows without erroring — and
thousands of DOM nodes nobody scrolls to.
"""
from fastapi import HTTPException

from app.repositories.learner_repository import LearnerRepository
from app.schemas.dto import LearnerListItem, LearnerPage

# Cards per page. Big enough that the grid fills a desktop viewport, small enough that a page is
# a cheap request against a table of thousands.
PER_PAGE = 24
MAX_PER_PAGE = 100


class LearnerService:
    def __init__(self):
        self.learners = LearnerRepository()

    def list_learners(
        self,
        *,
        page: int = 1,
        per_page: int = PER_PAGE,
        query: str | None = None,
        caseload_only: bool = True,
    ) -> LearnerPage:
        """One page of learners.

        `caseload_only` defaults TRUE: the Learners tab is where a therapist works with their own
        learners, and opening it on 5,783 anonymised research rows would bury them. The cohort is
        one toggle away, and the analytics scatter shows it whole.

        `per_page` is clamped rather than trusted — it arrives from the query string, and an
        unbounded value would let a caller ask for the entire table in one request, which is the
        read this whole method exists to prevent.
        """
        page = max(1, page)
        per_page = max(1, min(per_page, MAX_PER_PAGE))

        rows, total = self.learners.list_page(
            limit=per_page,
            offset=(page - 1) * per_page,
            query=query,
            caseload_only=caseload_only,
        )
        return LearnerPage(
            items=[self._to_item(row) for row in rows],
            total=total,
            page=page,
            per_page=per_page,
        )

    def get_learner(self, learner_id: str) -> dict:
        learner = self.learners.find_by_id(learner_id)
        if not learner:
            raise HTTPException(status_code=404, detail="Learner not found")
        return learner

    @staticmethod
    def _to_item(row: dict) -> LearnerListItem:
        return LearnerListItem(
            id=str(row["id"]),
            student_id=row.get("student_id"),
            pseudonym=row.get("pseudonym") or "",
            tier=row.get("tier") or "",
            on_caseload=bool(row.get("on_caseload")),
            band=row.get("band"),
            band_group=row.get("band_group"),
            cluster_cohort=row.get("cluster_cohort"),
        )
