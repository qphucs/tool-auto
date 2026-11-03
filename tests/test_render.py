"""Dựng HTML → video bằng Chrome thật và FFmpeg, ở kích thước nhỏ cho test chạy nhanh."""

import shutil
import threading

import pytest

from app.automation.browser import find_chrome
from app.core.media import probe
from app.editor.ffmpeg import Cancelled, FFmpegError
from app.render.bench import DEMO_DATA
from app.render.html_renderer import METHODS, FrameJob, render, snapshot
from app.render.page import build_page, even_captions

pytestmark = pytest.mark.skipif(
    find_chrome() is None or shutil.which("ffmpeg") is None, reason="Cần Google Chrome và FFmpeg"
)

W, H = 270, 480


@pytest.fixture
def page(tmp_path):
    return build_page("hook", DEMO_DATA, 2.0, tmp_path / "p.html", even_captions("một hai ba bốn năm sáu", 0.2, 1.8))


def test_frames_are_deterministic(page):
    job = FrameJob(page, 2.0, W, H)
    first = snapshot(job, [0.0, 1.6])
    again = snapshot(job, [1.6])
    assert first[1] == again[0]  # nhảy tới 1.6 từ 0 hay mở mới đều ra cùng một khung hình
    assert first[0] != first[1]


@pytest.mark.parametrize("method", METHODS)
def test_render_methods(page, tmp_path, method):
    out = tmp_path / f"{method}.mp4"
    progress = []
    stats = render(FrameJob(page, 1.0, W, H), out, method, workers=2, report=lambda f, m: progress.append(f))
    info = probe(out)
    assert (info.width, info.height) == (W, H)
    assert info.duration == pytest.approx(1.0, abs=0.1)
    assert stats.frames == 30 and stats.workers == 2
    assert progress[-1] == 1.0
    assert not list(tmp_path.glob("_chunks_*"))  # thư mục tạm đã dọn


def test_text_is_never_html(tmp_path):
    data = dict(DEMO_DATA, line1="</script><b>chữ</b>", chips=[{"icon": "<img src=x>", "text": "a & b"}])
    page = build_page("hook", data, 1.0, tmp_path / "p.html")
    [shot] = snapshot(FrameJob(page, 1.0, W, H), [0.9])
    assert shot  # trang không vỡ


def test_errors(tmp_path):
    with pytest.raises(ValueError):
        build_page("khong-co", {}, 1.0, tmp_path / "x.html")

    broken = build_page("hook", DEMO_DATA, 1.0, tmp_path / "b.html")
    broken.write_text(broken.read_text(encoding="utf-8").replace('"hook"', '"mat-tich"'), encoding="utf-8")
    with pytest.raises(FFmpegError, match="Trang cảnh bị lỗi"):
        render(FrameJob(broken, 1.0, W, H), tmp_path / "b.mp4")


def test_cancel(page, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        render(FrameJob(page, 1.0, W, H), tmp_path / "c.mp4", cancel=cancel)
    assert not (tmp_path / "c.mp4").exists()
