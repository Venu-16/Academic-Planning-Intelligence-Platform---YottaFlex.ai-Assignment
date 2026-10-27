import pytest

from academic_planner import database


def test_postgres_engine_requires_an_explicit_database_url(monkeypatch):
    monkeypatch.setattr(database, "DATABASE_URL", None)

    with pytest.raises(RuntimeError, match="Set DATABASE_URL"):
        database.get_engine()


def test_postgres_engine_accepts_an_explicit_database_url():
    engine = database.get_engine("postgresql+psycopg://localhost/test_db")
    try:
        assert engine.url.database == "test_db"
    finally:
        engine.dispose()
