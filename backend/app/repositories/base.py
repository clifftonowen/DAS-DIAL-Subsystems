"""Base repository: shares the Supabase client + a table handle."""
from app.core.supabase_client import get_supabase


class BaseRepository:
    table: str = ""

    @property
    def db(self):
        return get_supabase().table(self.table)
