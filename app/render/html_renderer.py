"""Dựng trang HTML thành video: nhảy tới từng khung hình, chụp ảnh, đẩy thẳng vào FFmpeg.

Có thể chạy nhiều tab Chrome song song, mỗi tab dựng một đoạn khung hình liên tiếp,
rồi ghép các đoạn lại (không mã hóa lại).
"""

import asyncio
import base64
import logging
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.automation.browser import find_chrome
from app.editor.ffmpeg import Cancelled, FFmpegError, ffmpeg_bin, run

log = logging.getLogger(__name__)

# cdp_jpeg: gọi thẳng Chrome DevTools (nhanh nhất), pw_jpeg / pw_png: chụp qua Playwright
METHODS = ("cdp_jpeg", "pw_jpeg", "pw_png")
JPEG_QUALITY = 92
VIDEO_ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

Report = Callable[[float, str], None]


@dataclass(frozen=True)
class FrameJob:
    page: Path
    duration: float
    width: int
    height: int
    fps: int = 30

    @property
    def frames(self) -> int:
        return max(1, round(self.duration * self.fps))


@dataclass
class RenderStats:
    frames: int
    seconds: float
    method: str
    workers: int
    width: int
    height: int
    fps: int

    @property
    def render_fps(self) -> float:
        return self.frames / self.seconds if self.seconds else 0.0

    @property
    def realtime_factor(self) -> float:
        """Số giây dựng cho mỗi giây video (1.0 = nhanh bằng thời gian thực)."""
        return self.seconds / (self.frames / self.fps)


async def _launch(pw) -> Browser:
    kwargs = {"channel": "chrome"} if find_chrome() is not None else {}
    return await pw.chromium.launch(headless=True, args=["--font-render-hinting=none", "--hide-scrollbars"], **kwargs)


async def _open(browser: Browser, job: FrameJob) -> tuple[BrowserContext, Page]:
    ctx = await browser.new_context(viewport={"width": job.width, "height": job.height}, device_scale_factor=1)
    page = await ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.goto(job.page.as_uri())
    try:
        await page.wait_for_function("window.__ready === true", timeout=15_000)
    except Exception as e:
        raise FFmpegError(f"Trang cảnh bị lỗi: {'; '.join(errors) or e}") from e
    return ctx, page


async def _grab(page: Page, cdp, method: str, t: float) -> bytes:
    await page.evaluate("t => window.__seek(t)", t)
    if method == "cdp_jpeg":
        shot = await cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": JPEG_QUALITY, "optimizeForSpeed": True})
        return base64.b64decode(shot["data"])
    if method == "pw_jpeg":
        return await page.screenshot(type="jpeg", quality=JPEG_QUALITY)
    return await page.screenshot(type="png")


async def _render_chunk(
    browser: Browser, job: FrameJob, first: int, last: int, out: Path, method: str,
    tick: Callable[[], None], cancel: threading.Event | None,
) -> None:
    ctx, page = await _open(browser, job)
    cdp = await ctx.new_cdp_session(page) if method == "cdp_jpeg" else None
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_bin(), "-hide_banner", "-v", "error", "-y",
        "-f", "image2pipe", "-framerate", str(job.fps), "-c:v", "png" if method == "pw_png" else "mjpeg", "-i", "-",
        *VIDEO_ENC, "-r", str(job.fps), str(out),
        stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=_NO_WINDOW,
    )
    try:
        for i in range(first, last):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            proc.stdin.write(await _grab(page, cdp, method, i / job.fps))
            try:
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                break  # FFmpeg đã thoát, lỗi được đọc ở dưới
            tick()
        proc.stdin.close()
        err = (await proc.stderr.read()).decode("utf-8", "replace")
        if await proc.wait() != 0:
            raise FFmpegError(f"FFmpeg báo lỗi khi ghép khung hình:\n{err.strip()[-600:]}")
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        await ctx.close()


def _split(frames: int, workers: int, piece: int | None) -> list[tuple[int, int]]:
    """Chia khung hình [0, frames) thành các đoạn liên tiếp."""
    count = max(1, min(frames, workers if piece is None else -(-frames // piece)))
    bounds = [round(frames * k / count) for k in range(count + 1)]
    return list(zip(bounds, bounds[1:]))


async def render_jobs_async(
    jobs: list[tuple[FrameJob, Path]], method: str = "cdp_jpeg", workers: int = 3,
    report: Report | None = None, cancel: threading.Event | None = None, piece: int | None = 90,
) -> RenderStats:
    """Dựng nhiều trang (mỗi trang ra một file). Trang dài được chia thành đoạn ~piece khung hình
    để các tab chia nhau làm; piece=None thì chia đều mỗi trang cho đúng số tab."""
    if method not in METHODS:
        raise ValueError(f"Cách chụp không hợp lệ: {method}")
    if not jobs:
        return RenderStats(0, 0.0, method, workers, 0, 0, 30)
    started = time.perf_counter()
    total = sum(job.frames for job, _ in jobs)
    done = 0

    def tick() -> None:
        nonlocal done
        done += 1
        if report and (done % 10 == 0 or done == total):
            report(done / total, f"Đang dựng khung hình {done}/{total}")

    pieces: list[tuple[FrameJob, int, int, Path]] = []
    plans: list[tuple[Path, Path, list[Path]]] = []
    for n, (job, out) in enumerate(jobs):
        work = out.parent / f"_chunks_{out.stem}_{n}"
        work.mkdir(parents=True, exist_ok=True)
        parts = []
        for k, (first, last) in enumerate(_split(job.frames, workers, piece)):
            part = work / f"part_{k}.mp4"
            pieces.append((job, first, last, part))
            parts.append(part)
        plans.append((out, work, parts))

    queue = list(reversed(pieces))
    try:
        async with async_playwright() as pw:
            browser = await _launch(pw)

            async def worker() -> None:
                while queue:
                    job, first, last, part = queue.pop()
                    await _render_chunk(browser, job, first, last, part, method, tick, cancel)

            try:
                async with asyncio.TaskGroup() as tg:
                    for _ in range(max(1, min(workers, len(pieces)))):
                        tg.create_task(worker())
            except BaseExceptionGroup as group:
                raise group.exceptions[0] from None
            finally:
                await browser.close()
        for out, work, parts in plans:
            (work / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
            out.unlink(missing_ok=True)
            run(["-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy",
                 "-movflags", "+faststart", str(out)], cwd=work)
    finally:
        for _, work, _ in plans:
            shutil.rmtree(work, ignore_errors=True)

    first_job = jobs[0][0]
    stats = RenderStats(total, time.perf_counter() - started, method, workers, first_job.width, first_job.height, first_job.fps)
    log.info(
        "Dựng %d trang: %d khung %dx%d bằng %s x%d trong %.1fs (%.1f khung/giây)",
        len(jobs), total, stats.width, stats.height, method, workers, stats.seconds, stats.render_fps,
    )
    return stats


def render_jobs(jobs: list[tuple[FrameJob, Path]], method: str = "cdp_jpeg", workers: int = 3,
                report: Report | None = None, cancel: threading.Event | None = None, piece: int | None = 90) -> RenderStats:
    return asyncio.run(render_jobs_async(jobs, method, workers, report, cancel, piece))


def render(job: FrameJob, out: Path, method: str = "cdp_jpeg", workers: int = 2,
           report: Report | None = None, cancel: threading.Event | None = None) -> RenderStats:
    """Dựng một trang, chia đều cho `workers` tab."""
    return render_jobs([(job, out)], method, workers, report, cancel, piece=None)


async def _snapshot_async(job: FrameJob, times: list[float], method: str) -> list[bytes]:
    async with async_playwright() as pw:
        browser = await _launch(pw)
        try:
            ctx, page = await _open(browser, job)
            cdp = await ctx.new_cdp_session(page) if method == "cdp_jpeg" else None
            return [await _grab(page, cdp, method, t) for t in times]
        finally:
            await browser.close()


def snapshot(job: FrameJob, times: list[float], method: str = "pw_png") -> list[bytes]:
    """Chụp vài khung hình lẻ (dùng để xem nhanh và để test)."""
    return asyncio.run(_snapshot_async(job, times, method))
