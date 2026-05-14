from contextlib import contextmanager
from typing import Iterator, Optional


class DatabaseClient:
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url

    def is_configured(self) -> bool:
        return bool(self.database_url)

    def _connect(self):
        if not self.database_url:
            raise ValueError("DATABASE_URL fehlt.")
        try:
            import psycopg
        except ImportError as exc:
            raise ImportError(
                "Package 'psycopg' ist nicht installiert. "
                "Bitte `psycopg[binary]` in den Requirements aufnehmen."
            ) from exc
        return psycopg.connect(self.database_url)

    @contextmanager
    def connection(self) -> Iterator:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def ping(self) -> bool:
        if not self.is_configured():
            return False
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                row = cursor.fetchone()
        return bool(row and row[0] == 1)
