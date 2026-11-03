"""Chạy bộ đăng YouTube trên trang Studio giả bằng Chrome thật (không cần mạng hay tài khoản)."""

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from app.automation.browser import find_chrome
from app.uploaders import youtube
from app.uploaders.base import LoginRequired, NeedsAttention, UploadRequest
from app.uploaders.youtube import YouTubeUploader, load_selectors

pytestmark = pytest.mark.skipif(find_chrome() is None, reason="Cần Google Chrome")

FIXTURES = Path(__file__).parent / "fixtures"


def _selectors(studio_page: str = "fake_studio.html", mode: str = "") -> dict:
    sel = load_selectors()
    url = (FIXTURES / studio_page).as_uri() + (f"#{mode}" if mode else "")
    sel["urls"] = {"studio": url, "upload": url}
    sel["login_url_markers"] = ["fake_login"]
    return sel


@pytest.fixture
def pw():
    with sync_playwright() as p:
        yield p


@pytest.fixture
def kept_pages(monkeypatch):
    """Giữ trang mở sau khi upload xong để test đọc lại nội dung đã điền."""
    pages = []
    real_launch = youtube.launch_context

    def launch(pw, profile_dir, headless):
        ctx = real_launch(pw, profile_dir, True)
        real_close = ctx.close
        ctx.close = lambda: None
        pages.append((ctx, real_close))
        return ctx

    monkeypatch.setattr(youtube, "launch_context", launch)
    yield pages
    for _, close in pages:
        close()


def _request(tmp_path, video_file, **kw) -> UploadRequest:
    defaults = dict(
        video_path=video_file,
        title="Video thử nghiệm",
        description="Dòng 1\nDòng 2",
        hashtags=["#a", "#b"],
        visibility="unlisted",
        profile_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
        headless=True,
        timeout_s=30,
    )
    return UploadRequest(**(defaults | kw))


def test_upload_fills_everything(pw, tmp_path, video_file, kept_pages):
    result = YouTubeUploader(_selectors()).upload(pw, _request(tmp_path, video_file))
    assert result.url == "https://youtu.be/TEST123"

    page = kept_pages[0][0].pages[0]
    assert page.locator("#title-textarea #textbox").inner_text() == "Video thử nghiệm"
    # Ô contenteditable của Chrome có thể hiện thêm dòng trống, chỉ so các dòng có chữ
    lines = page.locator("#description-textarea #textbox").inner_text().split("\n")
    assert [line for line in lines if line] == ["Dòng 1", "Dòng 2", "#a #b"]
    assert page.locator("[name=VIDEO_MADE_FOR_KIDS_NOT_MFK]").get_attribute("checked") == ""
    assert page.locator("[name=UNLISTED]").get_attribute("checked") == ""
    assert page.locator("[name=PUBLIC]").get_attribute("checked") is None


def test_youtube_error_needs_attention_with_screenshot(pw, tmp_path, video_file):
    with pytest.raises(NeedsAttention, match="Daily upload limit") as exc:
        YouTubeUploader(_selectors(mode="error")).upload(pw, _request(tmp_path, video_file))
    assert "ảnh chụp màn hình" in str(exc.value)
    assert list((tmp_path / "shots").glob("youtube-*.png"))


def test_no_confirmation_is_not_retried(pw, tmp_path, video_file, monkeypatch):
    monkeypatch.setattr(youtube, "CONFIRM_TIMEOUT_MS", 2000)  # cho test chạy nhanh
    with pytest.raises(NeedsAttention, match="không thấy YouTube xác nhận"):
        YouTubeUploader(_selectors(mode="noconfirm")).upload(pw, _request(tmp_path, video_file))


def test_login_redirect(pw, tmp_path, video_file):
    login_sel = _selectors(studio_page="fake_login.html")
    uploader = YouTubeUploader(login_sel)
    assert uploader.check_login(pw, tmp_path / "profile") is False
    with pytest.raises(LoginRequired):
        uploader.upload(pw, _request(tmp_path, video_file))
    assert YouTubeUploader(_selectors()).check_login(pw, tmp_path / "profile") is True


def test_validate():
    u = YouTubeUploader(_selectors())
    assert u.validate("Ổn", "mô tả", ["#a"]) == []
    assert len(u.validate("", "a > b", ["#x"] * 61)) == 3
