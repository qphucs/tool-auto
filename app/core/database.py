from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import Base

# Tăng số này và thêm bước nâng cấp trong _migrate() mỗi khi đổi cấu trúc bảng đã có
SCHEMA_VERSION = 1


def _set_pragmas(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{path.as_posix()}")
        event.listen(self.engine, "connect", _set_pragmas)
        Base.metadata.create_all(self.engine)
        self._migrate()
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def _migrate(self) -> None:
        with self.engine.begin() as conn:
            version = conn.execute(text("PRAGMA user_version")).scalar() or 0
            if version < SCHEMA_VERSION:
                conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))

    def session(self) -> Session:
        return self._sessions()

    def close(self) -> None:
        self.engine.dispose()
