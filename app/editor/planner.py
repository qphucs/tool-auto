"""Quyết định lấy đoạn nào của video gốc, dài bao nhiêu, theo nhịp của video mẫu.

Các video gốc được nối thành một dòng thời gian ảo. Đoạn được rải đều trên dòng thời gian
(theo thứ tự) và nhích về điểm chuyển cảnh gần nhất của video gốc để chỗ cắt tự nhiên hơn.
"""

import bisect
from dataclasses import dataclass

from app.editor.template import TemplateSpec

MIN_SEGMENT = 0.3
SNAP_WINDOW = 1.0
MAX_CLIPS = 10

MODE_LABELS = {
    "auto": "Tự động chọn",
    "rhythm": "Cắt ghép theo nhịp của mẫu",
    "split": "Cắt video dài thành nhiều clip",
    "keep": "Giữ nguyên nội dung (chỉ đổi khung hình, màu, chữ)",
}


@dataclass(frozen=True)
class Segment:
    source: int  # vị trí video gốc trong danh sách
    start: float  # giây, tính trong video gốc đó
    duration: float


def sequence_durations(shots: list[float], target: float) -> list[float]:
    """Lặp lại nhịp cảnh của mẫu cho đủ thời lượng target."""
    shots = [s for s in shots if s > 0] or [target]
    out: list[float] = []
    total = 0.0
    i = 0
    while total < target - 1e-6:
        d = min(shots[i % len(shots)], target - total)
        out.append(d)
        total += d
        i += 1
    if len(out) > 1 and out[-1] < MIN_SEGMENT:
        last = out.pop()
        out[-1] += last
    return out


def _offsets(src_durs: list[float]) -> list[float]:
    offsets = [0.0]
    for d in src_durs[:-1]:
        offsets.append(offsets[-1] + d)
    return offsets


def _snap(pos: float, cuts: list[float], lo: float, hi: float) -> float:
    near = [c for c in cuts if abs(c - pos) <= SNAP_WINDOW and lo <= c <= hi]
    if near:
        return min(near, key=lambda c: abs(c - pos))
    return min(max(pos, lo), max(lo, hi))


def place_segments(
    durations: list[float], src_durs: list[float], cuts: list[float], w0: float, w1: float
) -> list[Segment]:
    """Rải các đoạn có độ dài `durations` trong khoảng [w0, w1] của dòng thời gian ảo."""
    offsets = _offsets(src_durs)
    span = w1 - w0
    durs = list(durations)
    while durs and sum(durs) > span:
        durs.pop()
    if not durs:
        durs = [span]
    gap = (span - sum(durs)) / len(durs)

    segments = []
    pos, prev_end = w0 + gap / 2, w0
    for d in durs:
        start = _snap(pos, cuts, prev_end, w1 - d)
        idx = max(0, bisect.bisect_right(offsets, start) - 1)
        local = start - offsets[idx]
        file_dur = src_durs[idx]
        if local + d > file_dur:  # không cho đoạn tràn sang video gốc kế tiếp
            local = max(0.0, file_dur - d)
            d = min(d, file_dur)
        segments.append(Segment(idx, round(local, 3), round(d, 3)))
        prev_end = offsets[idx] + local + d
        pos = max(prev_end, start + d) + gap
    return segments


def resolve_mode(mode: str, spec: TemplateSpec, src_durs: list[float]) -> str:
    if mode != "auto":
        return mode
    total = sum(src_durs)
    target = spec.duration or total
    if len(src_durs) == 1 and total <= target * 1.3:
        return "keep"
    if len(src_durs) == 1 and total >= target * 3:
        return "split"
    return "rhythm"


def default_clip_count(spec: TemplateSpec, total: float) -> int:
    target = spec.duration or 30
    return max(1, min(MAX_CLIPS, int(total // target)))


def plan(mode: str, spec: TemplateSpec, src_durs: list[float], cuts: list[float], clip_count: int = 0) -> list[list[Segment]]:
    """Mỗi phần tử là danh sách đoạn của một video thành phẩm."""
    total = sum(src_durs)
    if mode == "keep":
        return [[Segment(i, 0.0, round(d, 3))] for i, d in enumerate(src_durs)]
    if mode == "rhythm":
        target = min(spec.duration or total, total)
        return [place_segments(sequence_durations(spec.shot_durations, target), src_durs, cuts, 0.0, total)]
    if mode == "split":
        count = clip_count or default_clip_count(spec, total)
        window = total / count
        target = min(spec.duration or window, window)
        durations = sequence_durations(spec.shot_durations, target)
        return [place_segments(durations, src_durs, cuts, k * window, (k + 1) * window) for k in range(count)]
    raise ValueError(f"Cách dựng không hợp lệ: {mode}")
