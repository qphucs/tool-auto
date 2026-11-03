"""Ghép các cảnh thành một video ngắn.

Mỗi cảnh dựng thành một file riêng và được lưu vào bộ nhớ đệm theo nội dung của nó, nên khi sửa
một cảnh chỉ cảnh đó phải dựng lại. Sau đó nối các cảnh, đặt giọng đọc của từng cảnh vào đúng chỗ
và trộn nhạc nền nhỏ phía dưới.
"""

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.core.settings import BrandSettings
from app.editor.ffmpeg import run
from app.render.html_renderer import FrameJob, render_jobs
from app.render.page import assets_version, brand_payload, build_page

log = logging.getLogger(__name__)

FPS = 30
AUDIO_LEAD = 0.25  # giọng đọc bắt đầu sau khi cảnh hiện 0.25 giây
MUSIC_VOLUME = 0.12  # nhạc nền khi có giọng đọc
MUSIC_ONLY_VOLUME = 0.5
DRAFT_SIZE = (540, 960)
FINAL_SIZE = (1080, 1920)

Report = Callable[[float, str], None]


@dataclass
class SceneInput:
    type: str
    data: dict
    duration: float
    captions: list[dict] = field(default_factory=list)  # mốc thời gian tính trong cảnh, đã cộng AUDIO_LEAD
    audio: Path | None = None


@dataclass
class ClipResult:
    path: Path
    scene_files: list[Path]
    rendered: int  # số cảnh phải dựng lại (không có sẵn trong bộ nhớ đệm)
    duration: float


def scene_seconds(scene: SceneInput) -> float:
    """Độ dài thật của cảnh sau khi làm tròn theo khung hình."""
    return max(1, round(scene.duration * FPS)) / FPS


def scene_key(scene: SceneInput, index: int, size: tuple[int, int], brand: dict) -> str:
    image = scene.data.get("image")
    image_stamp = Path(image).stat().st_mtime if image and Path(image).is_file() else None
    payload = [assets_version(), scene.type, scene.data, scene_seconds(scene), scene.captions, size, brand, index, image_stamp]
    return hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def _mix_audio(scenes: list[SceneInput], video: Path, out: Path, music: Path | None, cancel: threading.Event | None) -> None:
    durations = [scene_seconds(s) for s in scenes]
    total = sum(durations)
    has_voice = any(s.audio for s in scenes)
    if not has_voice and music is None:
        run(["-y", "-v", "error", "-i", str(video), "-c", "copy", "-movflags", "+faststart", str(out)], cancel=cancel)
        return

    inputs = ["-i", str(video)]
    filters, labels = [], []
    index = 1
    lead = int(AUDIO_LEAD * 1000)
    for i, (s, d) in enumerate(zip(scenes, durations)):
        if s.audio:
            inputs += ["-i", str(s.audio)]
            filters.append(
                f"[{index}:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={lead}|{lead},apad,atrim=0:{d:.3f}[s{i}]"
            )
            index += 1
        else:
            filters.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{d:.3f}[s{i}]")
        labels.append(f"[s{i}]")
    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[voice]")
    final = "[voice]"
    if music is not None:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        volume = MUSIC_VOLUME if has_voice else MUSIC_ONLY_VOLUME
        filters.append(
            f"[{index}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={volume},atrim=0:{total:.3f},"
            f"afade=t=in:d=1,afade=t=out:st={max(0.0, total - 1.5):.3f}:d=1.5[music]"
        )
        filters.append("[voice][music]amix=inputs=2:duration=first:normalize=0[mix]")
        final = "[mix]"
    run(
        ["-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "0:v", "-map", final,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)],
        cancel=cancel,
    )


def render_clip(
    scenes: list[SceneInput], out: Path, cache_dir: Path, size: tuple[int, int] = FINAL_SIZE,
    brand: BrandSettings | None = None, music: Path | None = None, report: Report | None = None,
    cancel: threading.Event | None = None, workers: int = 3,
) -> ClipResult:
    if not scenes:
        raise ValueError("Clip chưa có cảnh nào")
    report = report or (lambda f, m: None)
    brand_data = brand_payload(brand or BrandSettings())
    width, height = size
    cache_dir.mkdir(parents=True, exist_ok=True)

    files, jobs = [], []
    for i, scene in enumerate(scenes):
        key = scene_key(scene, i, size, brand_data)
        video = cache_dir / f"scene-{key}-{width}x{height}.mp4"
        files.append(video)
        if not video.exists():
            page = build_page(scene.type, scene.data, scene_seconds(scene), cache_dir / f"scene-{key}.html",
                              scene.captions, brand_data, seed=7 + i, bg_offset=i * 13.0)
            jobs.append((FrameJob(page, scene_seconds(scene), width, height, FPS), video))

    report(0.0, f"Cần dựng {len(jobs)}/{len(scenes)} cảnh")
    render_jobs(jobs, workers=workers, cancel=cancel, report=lambda f, m: report(0.9 * f, m))

    report(0.92, "Đang ghép cảnh và âm thanh")
    joined = cache_dir / f"_joined-{out.stem}.mp4"
    list_file = cache_dir / f"_list-{out.stem}.txt"
    list_file.write_text("".join(f"file '{f.name}'\n" for f in files), encoding="utf-8")
    try:
        run(["-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", list_file.name, "-c", "copy", joined.name],
            cwd=cache_dir, cancel=cancel)
        out.parent.mkdir(parents=True, exist_ok=True)
        _mix_audio(scenes, joined, out, music, cancel)
    finally:
        joined.unlink(missing_ok=True)
        list_file.unlink(missing_ok=True)
    report(1.0, "Xong")
    duration = sum(scene_seconds(s) for s in scenes)
    log.info("Ghép clip %s: %d cảnh (%d dựng mới), %.1f giây", out.name, len(scenes), len(jobs), duration)
    return ClipResult(out, files, len(jobs), duration)
