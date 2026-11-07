"""Database URL handling must fail closed and support isolated SQLite tests."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class DatabaseSessionTests(unittest.TestCase):
    def test_engine_requires_a_database_url(self) -> None:
        from app.db.session import build_engine

        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is required"):
                build_engine()

    def test_engine_uses_configured_sqlite_database(self) -> None:
        from app.db.models import Base
        from app.db.session import build_engine

        engine = build_engine("sqlite://")
        try:
            Base.metadata.create_all(engine)
            self.assertIn("projects", inspect(engine).get_table_names())
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
