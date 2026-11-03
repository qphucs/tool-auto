"""Mở trình duyệt cho từng tài khoản.

- Đăng nhập: mở Chrome bình thường (không tự động hóa) để người dùng tự đăng nhập.
- Đăng bài: Playwright dùng lại đúng hồ sơ Chrome đó, nên không cần đăng nhập lại.
"""

import os
import subprocess
from pathlib import Path

from playwright.sync_api import BrowserContext, Playwright


class BrowserNotFound(Exception):
    pass


def _chrome_candidates() -> list[Path]:
    roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    return [Path(r) / "Google" / "Chrome" / "Application" / "chrome.exe" for r in roots if r]


def find_chrome() -> Path | None:
    return next((p for p in _chrome_candidates() if p.is_file()), None)


def open_login_window(profile_dir: Path, url: str) -> subprocess.Popen:
    chrome = find_chrome()
    if chrome is None:
        raise BrowserNotFound("Không tìm thấy Google Chrome. Hãy cài Chrome rồi thử lại.")
    profile_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            str(chrome),
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            url,
        ]
    )


def launch_context(pw: Playwright, profile_dir: Path, headless: bool) -> BrowserContext:
    profile_dir.mkdir(parents=True, exist_ok=True)
    kwargs = {}
    if find_chrome() is not None:
        kwargs["channel"] = "chrome"
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        **kwargs,
    )
