"""Tìm Google Chrome để Playwright dùng (dựng hình từ HTML, chụp trang web)."""

import os
from pathlib import Path


def _chrome_candidates() -> list[Path]:
    roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    return [Path(r) / "Google" / "Chrome" / "Application" / "chrome.exe" for r in roots if r]


def find_chrome() -> Path | None:
    return next((p for p in _chrome_candidates() if p.is_file()), None)
