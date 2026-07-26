"""UserRepository - the `users` table, our mirror of the Supabase Auth users.

Speaks in `Therapist` entities (the type both the class diagram and the UC6/UC8
sequence diagrams name), not in raw rows.
"""
from app.entities.models import Therapist
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    table = "users"

    def save(self, therapist: Therapist) -> Therapist:
        """UC8 `save(therapist)`. Upsert, so a repeat save is idempotent.

        `mode="json"` serialises the UUID fields to strings for PostgREST.
        """
        self.db.upsert(therapist.model_dump(mode="json")).execute()
        return therapist

    def find_by_email(self, email: str) -> Therapist | None:
        """UC6 `findByEmail(email)`. `None` when the therapist has no mirror row."""
        rows = self.db.select("*").eq("email", email).execute().data
        if not rows:
            return None
        # Drop NULL columns so the entity's own defaults apply (`name` is
        # nullable in infra/schema.sql but non-optional on Therapist).
        return Therapist(**{k: v for k, v in rows[0].items() if v is not None})
