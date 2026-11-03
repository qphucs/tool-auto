"""Khung hình từ video gốc: ứng viên để AI chọn làm hình minh họa, và tách khung hình độ phân giải cao."""

import threading
from pathlib import Path

from app.editor.ffmpeg import run

GRID_STEP = 8.0  # ngoài điểm chuyển cảnh, cứ 8 giây lấy thêm một khung
MIN_GAP = 2.0  # bỏ các khung quá sát nhau
THUMB_WIDTH = 640


def candidate_times(cuts: list[float], start: float, end: float, max_frames: int = 16) -> list[float]:
    """Thời điểm lấy khung: ngay sau mỗi chuyển cảnh và theo lưới đều, bỏ trùng, tối đa max_frames."""
    times = [c + 0.5 for c in cuts if start <= c + 0.5 < end]
    t = start + GRID_STEP / 2
    while t < end:
        times.append(t)
        t += GRID_STEP
    kept: list[float] = []
    for t in sorted(times):
        if not kept or t - kept[-1] >= MIN_GAP:
            kept.append(round(t, 2))
    if len(kept) > max_frames:
        step = len(kept) / max_frames
        kept = [kept[int(i * step)] for i in range(max_frames)]
    return kept


def extract_frame(video: Path, t: float, out: Path, width: int = 1280, cancel: threading.Event | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        run(["-y", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(video), "-frames:v", "1",
             "-vf", f"scale='min({width},iw)':-2", "-q:v", "2", str(out)], cancel=cancel)
    return out


def candidate_frames(video: Path, cuts: list[float], start: float, end: float, out_dir: Path,
                     cancel: threading.Event | None = None, max_frames: int = 16) -> list[tuple[float, Path]]:
    frames = []
    for t in candidate_times(cuts, start, end, max_frames):
        frames.append((t, extract_frame(video, t, out_dir / f"thumb-{t:08.2f}.jpg", THUMB_WIDTH, cancel)))
    return frames
