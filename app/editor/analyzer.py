"""Đo các đặc điểm của video bằng FFmpeg (không dùng AI)."""

import re
import threading
from pathlib import Path

from app.core.media import VideoInfo, probe
from app.editor.ffmpeg import FFmpegError, run
from app.editor.template import TemplateSpec

SCENE_THRESHOLD = 0.3  # 0-1, càng nhỏ càng nhạy với chuyển cảnh
MIN_SHOT = 0.15  # cảnh ngắn hơn mức này coi như nhiễu, gộp vào cảnh trước
STATS_SECONDS = 300  # chỉ đo màu trong 5 phút đầu để video dài không chạy quá lâu


def detect_cuts(path: Path, cancel: threading.Event | None = None) -> list[float]:
    """Các thời điểm (giây) có chuyển cảnh."""
    _, err = run(
        ["-v", "info", "-i", str(path), "-an",
         "-vf", f"scale=160:-2,select='gt(scene,{SCENE_THRESHOLD})',showinfo",
         "-f", "null", "-"],
        cancel=cancel,
    )
    return sorted(float(t) for t in re.findall(r"pts_time:([\d.]+)", err))


def shot_durations(cuts: list[float], duration: float) -> list[float]:
    points = [0.0] + [c for c in cuts if 0.05 < c < duration - 0.05] + [duration]
    shots: list[float] = []
    for a, b in zip(points, points[1:]):
        d = b - a
        if shots and d < MIN_SHOT:
            shots[-1] += d
        elif d > 0:
            shots.append(d)
    return [round(s, 3) for s in shots]


def color_stats(path: Path, cancel: threading.Event | None = None) -> tuple[float, float] | None:
    """(độ sáng trung bình, độ đậm màu trung bình) hoặc None nếu không đo được."""
    out, _ = run(
        ["-v", "error", "-t", str(STATS_SECONDS), "-i", str(path), "-an",
         "-vf", "fps=2,scale=160:-2,signalstats,metadata=print:file=-",
         "-f", "null", "-"],
        cancel=cancel,
    )
    y = [float(v) for v in re.findall(r"signalstats\.YAVG=([\d.]+)", out)]
    s = [float(v) for v in re.findall(r"signalstats\.SATAVG=([\d.]+)", out)]
    if not y or not s:
        return None
    return sum(y) / len(y), sum(s) / len(s)


def has_black_bars(path: Path, info: VideoInfo, cancel: threading.Event | None = None) -> bool:
    _, err = run(
        ["-v", "info", "-t", "60", "-i", str(path), "-an",
         "-vf", "fps=2,cropdetect=limit=24:round=2:reset=0",
         "-f", "null", "-"],
        cancel=cancel,
    )
    crops = re.findall(r"crop=(\d+):(\d+):\d+:\d+", err)
    if not crops or not info.width or not info.height:
        return False
    w, h = map(int, crops[-1])
    ratio = (w * h) / (info.width * info.height)
    # Dưới 30% nhiều khả năng là video tối chứ không phải viền đen
    return 0.3 < ratio < 0.9


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def output_size(width: int, height: int) -> tuple[int, int]:
    """Giữ tỉ lệ của mẫu, cạnh ngắn trong khoảng 720-1080."""
    short = min(width, height)
    scale = max(720, min(1080, short)) / short
    return _even(width * scale), _even(height * scale)


def analyze_sample(path: Path, cancel: threading.Event | None = None) -> TemplateSpec:
    info = probe(path)
    if not info.duration or not info.width or not info.height:
        raise FFmpegError(f"Không đọc được video mẫu: {path.name}")
    shots = shot_durations(detect_cuts(path, cancel), info.duration)
    width, height = output_size(info.width, info.height)
    stats = color_stats(path, cancel)
    return TemplateSpec(
        width=width,
        height=height,
        fps=min(60, max(24, round(info.fps or 30))),
        framing="pad" if has_black_bars(path, info, cancel) else "crop",
        shot_durations=shots,
        duration=round(info.duration, 2),
        brightness=round(stats[0], 1) if stats else None,
        saturation=round(stats[1], 1) if stats else None,
        sample_file=str(path),
    )
