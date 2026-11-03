import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Không bật cửa sổ console đen khi app chạy bằng pythonw
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class VideoInfo:
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    has_audio: bool = False

    @property
    def is_vertical(self) -> bool:
        return bool(self.width and self.height and self.height > self.width)

    def describe(self) -> str:
        if self.duration is None and self.width is None:
            return "Không đọc được thông tin video."
        parts = []
        if self.width and self.height:
            parts.append(f"{self.width}x{self.height}")
            parts.append("dọc" if self.is_vertical else "ngang")
        if self.duration is not None:
            minutes, seconds = divmod(round(self.duration), 60)
            parts.append(f"{minutes:02d}:{seconds:02d}")
        return " · ".join(parts)


def _parse_rate(rate: str | None) -> float | None:
    try:
        num, _, den = (rate or "").partition("/")
        value = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return value or None


def probe(path: Path) -> VideoInfo:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        log.warning("Không tìm thấy ffprobe")
        return VideoInfo()
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "stream=codec_type,width,height,avg_frame_rate:format=duration",
        "-of", "json", str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW, check=True)
        data = json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        log.warning("ffprobe không đọc được %s: %s", path, e)
        return VideoInfo()
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    duration = data.get("format", {}).get("duration")
    return VideoInfo(
        duration=float(duration) if duration else None,
        width=video.get("width"),
        height=video.get("height"),
        fps=_parse_rate(video.get("avg_frame_rate")),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )
