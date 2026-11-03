import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Không đụng vào settings.json thật trong AppData."""
    monkeypatch.setenv("TOOLAUTO_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path / "config"


@pytest.fixture
def db(tmp_path):
    from app.core.database import Database

    database = Database(tmp_path / "data" / "toolauto.db")
    yield database
    database.close()


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def ctx(qapp, tmp_path, db):
    from app.core.settings import Settings
    from app.ui.services import create_context

    context = create_context(Settings(data_dir=str(tmp_path / "data")), db)
    yield context
    context.scheduler.stop()
    context.worker.stop()


@pytest.fixture
def video_file(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"not really a video")
    return path
