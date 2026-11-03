"""Đọc, cắt ghép và ghi phụ đề SRT."""

import re
from dataclasses import dataclass

from app.editor.planner import Segment

_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def _seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def parse_srt(text: str) -> list[Cue]:
    cues = []
    for block in re.split(r"\n\s*\n", text.lstrip("﻿").replace("\r\n", "\n")):
        lines = block.strip().split("\n")
        for i, line in enumerate(lines):
            m = _TIME.search(line)
            if m:
                body = "\n".join(lines[i + 1 :]).strip()
                if body:
                    g = m.groups()
                    cues.append(Cue(_seconds(*g[:4]), _seconds(*g[4:]), body))
                break
    return cues


def remap(cues: list[Cue], segments: list[Segment]) -> list[Cue]:
    """Dời phụ đề theo các đoạn đã cắt (tất cả đoạn lấy từ cùng một video gốc)."""
    out: list[Cue] = []
    t = 0.0
    for seg in segments:
        end = seg.start + seg.duration
        for c in cues:
            if c.end > seg.start and c.start < end:
                out.append(Cue(max(c.start, seg.start) - seg.start + t, min(c.end, end) - seg.start + t, c.text))
        t += seg.duration
    return out


def _fmt(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    return "\n".join(f"{i}\n{_fmt(c.start)} --> {_fmt(c.end)}\n{c.text}\n" for i, c in enumerate(cues, 1))
