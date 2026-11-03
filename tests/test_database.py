from sqlalchemy import text

from app.core.database import SCHEMA_VERSION


def test_pragmas_and_schema_version(db):
    with db.session() as session:
        assert session.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert session.execute(text("PRAGMA user_version")).scalar() == SCHEMA_VERSION
    assert db.path.exists()
