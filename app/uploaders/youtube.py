import logging
import time
from datetime import datetime
from pathlib import Path

import yaml
from playwright.sync_api import BrowserContext, Page, Playwright
from playwright.sync_api import Error as PlaywrightError

from app.automation.browser import launch_context
from app.core.models import Platform
from app.uploaders.base import (
    LoginRequired,
    NeedsAttention,
    UploadError,
    UploadRequest,
    UploadResult,
    Uploader,
)

log = logging.getLogger(__name__)

SELECTORS_FILE = Path(__file__).parent / "selectors" / "youtube.yaml"
TITLE_MAX = 100
DESCRIPTION_MAX = 5000
HASHTAG_MAX = 60
PAGE_TIMEOUT_MS = 30_000
CONFIRM_TIMEOUT_MS = 60_000


def load_selectors() -> dict:
    return yaml.safe_load(SELECTORS_FILE.read_text(encoding="utf-8"))


def _first_page(ctx: BrowserContext) -> Page:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_default_timeout(PAGE_TIMEOUT_MS)
    return page


def _short(e: Exception) -> str:
    return (str(e).strip().splitlines() or [e.__class__.__name__])[0][:300]


class YouTubeUploader(Uploader):
    platform = Platform.YOUTUBE

    def __init__(self, selectors: dict | None = None):
        self._selectors = selectors

    def selectors(self) -> dict:
        # Đọc lại file mỗi lần để sửa selector không cần khởi động lại app
        return self._selectors or load_selectors()

    @property
    def login_url(self) -> str:
        return self.selectors()["urls"]["studio"]

    @staticmethod
    def compose_description(description: str, hashtags: list[str]) -> str:
        text = description.strip()
        if hashtags:
            text = f"{text}\n\n{' '.join(hashtags)}" if text else " ".join(hashtags)
        return text

    def validate(self, title: str, description: str, hashtags: list[str]) -> list[str]:
        problems = []
        if not title.strip():
            problems.append("Tiêu đề không được để trống.")
        if len(title) > TITLE_MAX:
            problems.append(f"Tiêu đề YouTube tối đa {TITLE_MAX} ký tự (đang có {len(title)}).")
        if "<" in title or ">" in title:
            problems.append("Tiêu đề YouTube không được chứa dấu < hoặc >.")
        full = self.compose_description(description, hashtags)
        if len(full) > DESCRIPTION_MAX:
            problems.append(f"Mô tả kèm hashtag tối đa {DESCRIPTION_MAX} ký tự (đang có {len(full)}).")
        if "<" in full or ">" in full:
            problems.append("Mô tả YouTube không được chứa dấu < hoặc >.")
        if len(hashtags) > HASHTAG_MAX:
            problems.append(f"YouTube bỏ qua toàn bộ hashtag nếu có hơn {HASHTAG_MAX} hashtag.")
        return problems

    # ----- kiểm tra đăng nhập -----

    def check_login(self, pw: Playwright, profile_dir: Path, headless: bool = True) -> bool:
        sel = self.selectors()
        ctx = launch_context(pw, profile_dir, headless)
        try:
            page = _first_page(ctx)
            page.goto(sel["urls"]["studio"], wait_until="domcontentloaded")
            return self._wait_page_state(page, sel, sel["studio_ready"]) == "ready"
        finally:
            ctx.close()

    def _wait_page_state(self, page: Page, sel: dict, ready_selector: str, timeout_s: float = 45) -> str:
        """Chờ tới khi trang sẵn sàng ("ready") hoặc bị chuyển sang trang đăng nhập ("login")."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            url = page.url
            if any(m in url for m in sel["login_url_markers"]):
                return "login"
            if any(m in url for m in sel.get("no_channel_markers", [])):
                raise NeedsAttention("Tài khoản Google này chưa có kênh YouTube. Hãy tạo kênh trước.")
            try:
                if page.locator(ready_selector).count() > 0:
                    return "ready"
            except PlaywrightError:
                pass  # trang đang chuyển hướng
            page.wait_for_timeout(500)
        raise UploadError("YouTube Studio không phản hồi, có thể mạng chậm.")

    # ----- đăng video -----

    def upload(self, pw: Playwright, req: UploadRequest) -> UploadResult:
        sel = self.selectors()
        s = sel["upload"]
        description = self.compose_description(req.description, req.hashtags)
        ctx = launch_context(pw, req.profile_dir, req.headless)
        page: Page | None = None
        try:
            page = _first_page(ctx)
            page.goto(sel["urls"]["upload"], wait_until="domcontentloaded")
            if self._wait_page_state(page, sel, s["file_input"]) == "login":
                raise LoginRequired("Phiên đăng nhập YouTube đã hết hạn. Vào trang Tài khoản và bấm Đăng nhập.")

            page.set_input_files(s["file_input"], str(req.video_path))
            self._wait_visible(page, s, s["title"], timeout_s=120)
            self._fill(page, s["title"], req.title.replace("\n", " "))
            self._fill(page, s["description"], description)
            page.locator(s["not_made_for_kids"]).first.click()

            for _ in range(3):  # Chi tiết → Thành phần video → Kiểm tra → Chế độ hiển thị
                self._raise_if_error(page, s)
                page.locator(s["next_button"]).first.click()
                page.wait_for_timeout(1000)
            page.locator(s["visibility"][req.visibility]).first.click()

            url = self._video_url(page, s)
            self._wait_upload_done(page, s, req.timeout_s)
            page.locator(s["done_button"]).first.click()
            self._wait_finished_dialog(page, s)
            log.info("Đã đăng YouTube: %s %s", req.title, url)
            return UploadResult(url=url)
        except UploadError as e:
            raise type(e)(f"{e}{self._screenshot(page, req)}") from e
        except PlaywrightError as e:
            raise UploadError(f"Lỗi khi thao tác YouTube Studio: {_short(e)}{self._screenshot(page, req)}") from e
        finally:
            ctx.close()

    @staticmethod
    def _fill(page: Page, selector: str, text: str) -> None:
        page.locator(selector).first.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        for i, line in enumerate(text.split("\n")):
            if i:
                page.keyboard.press("Enter")
            if line:
                page.keyboard.insert_text(line)

    @staticmethod
    def _raise_if_error(page: Page, s: dict) -> None:
        box = page.locator(s["error"]).first
        if box.count() and box.is_visible():
            text = box.inner_text().strip()
            if text:
                raise NeedsAttention(f"YouTube báo: {text}")

    def _wait_visible(self, page: Page, s: dict, selector: str, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while not page.locator(selector).first.is_visible():
            self._raise_if_error(page, s)
            if time.monotonic() > deadline:
                raise UploadError("Không thấy hộp thoại tải lên của YouTube Studio.")
            page.wait_for_timeout(500)

    @staticmethod
    def _video_url(page: Page, s: dict) -> str:
        try:
            return page.locator(s["video_link"]).first.get_attribute("href") or ""
        except PlaywrightError:
            return ""

    def _wait_upload_done(self, page: Page, s: dict, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        uploading_texts = [t.lower() for t in s["uploading_texts"]]
        while True:
            self._raise_if_error(page, s)
            label = page.locator(s["progress_label"]).first
            text = label.inner_text().lower() if label.count() else ""
            uploading = any(t in text for t in uploading_texts)
            done_enabled = page.locator(s["done_button"]).first.evaluate(
                "el => !el.hasAttribute('disabled') && el.getAttribute('aria-disabled') !== 'true'"
            )
            if not uploading and done_enabled:
                return
            if time.monotonic() > deadline:
                raise UploadError("Quá thời gian chờ tải video lên YouTube.")
            page.wait_for_timeout(2000)

    @staticmethod
    def _wait_finished_dialog(page: Page, s: dict) -> None:
        try:
            page.locator(s["finished_dialogs"]).first.wait_for(state="visible", timeout=CONFIRM_TIMEOUT_MS)
        except PlaywrightError as e:
            # Đã bấm Đăng nhưng không thấy xác nhận: không tự thử lại để tránh đăng trùng
            raise NeedsAttention(
                "Đã bấm Đăng nhưng không thấy YouTube xác nhận. Kiểm tra trong YouTube Studio xem video đã lên chưa."
            ) from e
        close = page.locator(s["close_finished_dialog"]).first
        try:
            if close.count():
                close.click(timeout=5000)
        except PlaywrightError:
            pass
        page.wait_for_timeout(1500)

    @staticmethod
    def _screenshot(page: Page | None, req: UploadRequest) -> str:
        if page is None:
            return ""
        req.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = req.screenshot_dir / f"youtube-{datetime.now():%Y%m%d-%H%M%S}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
        except PlaywrightError:
            return ""
        return f" (ảnh chụp màn hình: {path})"
