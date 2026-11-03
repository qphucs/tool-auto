"""Chuẩn bị hình minh họa cho các cảnh: khung hình từ video gốc (AI chọn), ảnh chụp trang web."""

import asyncio
import hashlib
import logging
import threading
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright

from app.ai.base import AIError, AIProvider, extract_json
from app.automation.browser import find_chrome
from app.editor.ffmpeg import check_cancel
from app.pipeline.frames import candidate_frames, extract_frame
from app.pipeline.script import Scene, Script

log = logging.getLogger(__name__)

SEARCH_WINDOW = 15.0  # tìm khung hình quanh thời điểm AI gợi ý ±15 giây
VISION_CANDIDATES = 6

VISION_SYSTEM = "Bạn chọn ảnh minh họa cho video ngắn. Chỉ trả lời bằng JSON."


def _pick_frame(vision: AIProvider, scene: Scene, frames: list[tuple[float, Path]]) -> float | None:
    title = " ".join(str(scene.data.get(k, "")) for k in ("line1", "line2")).strip()
    prompt = (
        f"Cảnh video có tiêu đề: \"{title}\". Lời đọc: \"{scene.narration}\".\n"
        f"Đây là {len(frames)} khung hình (theo thứ tự 1..{len(frames)}) lấy từ video gốc. Ảnh sẽ được đặt trong khung "
        "trình duyệt để minh họa cho cảnh. Chọn ảnh rõ nét và đúng nội dung nhất. "
        'Nếu không ảnh nào hợp thì chọn 0. Trả về JSON: {"choice": số}'
    )
    data = extract_json(vision.complete(VISION_SYSTEM, prompt, [p for _, p in frames]))
    choice = int(data.get("choice", 0)) if isinstance(data, dict) else 0
    return frames[choice - 1][0] if 1 <= choice <= len(frames) else None


async def _capture(url: str, out: Path) -> None:
    kwargs = {"channel": "chrome"} if find_chrome() is not None else {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, **kwargs)
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                await page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass  # trang có kết nối chạy liên tục: chụp luôn
            await page.screenshot(path=str(out))
        finally:
            await browser.close()


def capture_web(url: str, out_dir: Path) -> Path:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Địa chỉ web không hợp lệ: {url}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"web-{hashlib.sha1(url.encode()).hexdigest()[:12]}.png"
    if not out.exists():
        asyncio.run(_capture(url, out))
    return out


def prepare_visuals(
    script: Script, video: Path, cuts: list[float], frames_dir: Path, out_dir: Path,
    vision: AIProvider | None = None, report: Callable[[float, str], None] | None = None,
    cancel: threading.Event | None = None,
) -> list[str]:
    """Điền visual.path cho các cảnh ảnh chụp. Trả về các cảnh báo (không dừng cả quá trình khi một ảnh lỗi)."""
    warnings = []
    targets = [s for s in script.scenes if s.type == "screenshot" and s.visual.kind in ("source", "web")]
    for i, scene in enumerate(targets):
        check_cancel(cancel)
        if report:
            report(i / max(1, len(targets)), f"Chuẩn bị hình minh họa {i + 1}/{len(targets)}")
        if scene.visual.path and Path(scene.visual.path).is_file():
            continue
        v = scene.visual
        try:
            if v.kind == "web":
                v.path = str(capture_web(v.url, out_dir))
            else:
                t = v.time if v.time is not None else (script.start + script.end) / 2
                lo, hi = max(script.start - 5, t - SEARCH_WINDOW), min(script.end + 5, t + SEARCH_WINDOW)
                if vision is not None and hi > lo:
                    frames = candidate_frames(video, cuts, lo, hi, frames_dir, cancel, VISION_CANDIDATES)
                    if frames:
                        try:
                            picked = _pick_frame(vision, scene, frames)
                            t = picked if picked is not None else t
                        except (AIError, ValueError, TypeError) as e:
                            warnings.append(f"AI chọn khung hình lỗi, dùng thời điểm gợi ý ({e}).")
                v.time = round(t, 2)
                v.path = str(extract_frame(video, t, out_dir / f"src-{t:08.2f}.jpg", 1280, cancel))
        except Exception as e:  # trang web không mở được, video lỗi...
            log.warning("Không chuẩn bị được hình cho cảnh: %s", e)
            warnings.append(f"Không lấy được hình ({v.kind}): {e}")
            v.path = ""
    return warnings
