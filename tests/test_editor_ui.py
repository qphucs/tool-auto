"""Chạy trọn luồng trên trang Dựng video: phân tích mẫu, dựng, lưu mẫu, dùng lại mẫu."""

import shutil
import subprocess
import time

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog

from app.core.models import StyleTemplate, Video
from app.ui.main_window import MainWindow
from app.ui.pages.editor import EditorPage
from app.ui.pages.templates import TemplatesPage

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="Cần ffmpeg")


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def _wait(ctx, timeout=60):
    deadline = time.monotonic() + timeout
    while ctx.media.running and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.05)
    QApplication.processEvents()
    assert not ctx.media.running


@pytest.fixture
def clips(tmp_path):
    sample = tmp_path / "mau.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "color=c=red:s=360x640:r=10:d=1",
        "-f", "lavfi", "-i", "color=c=blue:s=360x640:r=10:d=1",
        "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(sample),
    )
    source = tmp_path / "goc.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=5", "-pix_fmt", "yuv420p", str(source))
    return sample, source


def test_editor_full_flow(ctx, clips, monkeypatch):
    sample, source = clips
    window = MainWindow(ctx)
    page = next(p for p in window.pages if isinstance(p, EditorPage))

    page.analyze(sample)
    _wait(ctx)
    assert page.spec is not None and len(page.spec.shot_durations) == 2
    assert "720x1280" in page.sample_summary.text()

    page.sources.add_paths([source, source, sample.with_suffix(".txt")])
    assert page.sources.count() == 1  # bỏ trùng và bỏ file không phải video

    page.mode.setCurrentIndex(page.mode.findData("rhythm"))
    page.title_text.setText("Thử nghiệm")
    page._render()
    _wait(ctx)
    assert page.results.count() == 1
    assert "Xong: 1 video" in page.status.text()
    with ctx.db.session() as s:
        assert s.query(Video).count() == 1

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Mẫu đỏ xanh", True))
    page._save_template()
    with ctx.db.session() as s:
        assert s.query(StyleTemplate).one().name == "Mẫu đỏ xanh"

    templates = next(p for p in window.pages if isinstance(p, TemplatesPage))
    templates.on_show()
    assert templates.table.rowCount() == 1

    # Dùng lại mẫu đã lưu không cần phân tích lại
    page._set_spec(None)
    page.on_show()
    page.saved.setCurrentIndex(1)
    page._use_saved()
    assert page.spec is not None and page.spec.shot_durations == pytest.approx([1.0, 1.0], abs=0.15)
    window.close()


def test_editor_requires_inputs(ctx, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    window = MainWindow(ctx)
    page = next(p for p in window.pages if isinstance(p, EditorPage))
    assert page.build_job() is None
    assert "video mẫu" in warnings[0] and "video gốc" in warnings[0]
    window.close()
