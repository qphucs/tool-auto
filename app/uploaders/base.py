import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Playwright

from app.core.models import Platform

VISIBILITY_LABELS = {
    "public": "Công khai",
    "unlisted": "Không công khai",
    "private": "Riêng tư",
}


class UploadError(Exception):
    """Lỗi khi đăng; tool sẽ tự thử lại theo cài đặt."""


class NeedsAttention(UploadError):
    """Lỗi cần bạn xử lý (captcha, xác minh, giới hạn của nền tảng...). Không tự thử lại."""


class LoginRequired(NeedsAttention):
    """Phiên đăng nhập đã hết hạn."""


@dataclass
class UploadRequest:
    video_path: Path
    title: str
    description: str
    hashtags: list[str]
    visibility: str
    profile_dir: Path
    screenshot_dir: Path
    headless: bool = False
    timeout_s: int = 90 * 60


@dataclass
class UploadResult:
    url: str = ""


def parse_hashtags(text: str) -> list[str]:
    tags: list[str] = []
    for raw in re.split(r"[\s,]+", text or ""):
        tag = raw.strip().lstrip("#")
        if tag and f"#{tag}" not in tags:
            tags.append(f"#{tag}")
    return tags


class Uploader(ABC):
    platform: Platform

    @property
    @abstractmethod
    def login_url(self) -> str: ...

    @abstractmethod
    def check_login(self, pw: Playwright, profile_dir: Path, headless: bool = True) -> bool:
        """True nếu hồ sơ trình duyệt vẫn còn đăng nhập."""

    @abstractmethod
    def upload(self, pw: Playwright, req: UploadRequest) -> UploadResult: ...

    def validate(self, title: str, description: str, hashtags: list[str]) -> list[str]:
        """Danh sách vấn đề cần sửa trước khi đăng (rỗng = hợp lệ)."""
        return []
