"""Đo các đặc điểm của video bằng FFmpeg."""

import re
import threading
from pathlib import Path

from app.editor.ffmpeg import run

SCENE_THRESHOLD = 0.3  # 0-1, càng nhỏ càng nhạy với chuyển cảnh


def detect_cuts(path: Path, cancel: threading.Event | None = None, threshold: float = SCENE_THRESHOLD) -> list[float]:
    """Các thời điểm (giây) có chuyển cảnh."""
    _, err = run(
        ["-v", "info", "-i", str(path), "-an",
         "-vf", f"scale=160:-2,select='gt(scene,{threshold})',showinfo",
         "-f", "null", "-"],
        cancel=cancel,
    )
    return sorted(float(t) for t in re.findall(r"pts_time:([\d.]+)", err))
