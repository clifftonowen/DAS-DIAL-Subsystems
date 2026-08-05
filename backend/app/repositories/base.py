"""Base repository: shares the Supabase client + a table handle."""
from app.core.supabase_client import get_supabase


class StorageError(Exception):
    """The database could not be reached, or refused the operation.

    The repository-layer storage failure named throughout the UC2 test plan (UT-2.7,
    UT-2.11, IT-2.2, IT-2.4, ST-2.4). Repositories raise this instead of letting a raw
    supabase/httpx exception escape, so a service can distinguish "the database is
    unavailable" from "the data says no" without importing the driver's exception types.

    NOTE: `assessment_service` and `review_service` each define their own StorageError for
    their own boundaries. They are deliberately left alone — this one belongs to the
    repository layer and is the one the UC2 plan refers to.
    """


class BaseRepository:
    table: str = ""

    @property
    def db(self):
        return get_supabase().table(self.table)
