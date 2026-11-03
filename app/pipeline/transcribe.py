"""Chép lời video gốc bằng Whisper chạy trên máy (faster-whisper)."""

import json
import logging
import os
import threading
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from app.editor.ffmpeg import check_cancel, run

log = logging.getLogger(__name__)

# Gợi ý cho Whisper cách viết các thuật ngữ hay gặp trong video công nghệ (đo trên video thật: không có gợi ý
# thì "GitHub" thành "ghiết hấp", "PyPI" thành "pi pi"...)
TECH_TERMS = (
    "AI, ChatGPT, Claude, Gemini, Copilot, GitHub, repo, YouTube, TikTok, Facebook, Reddit, LinkedIn, Twitter, "
    "Chrome, Google, API, prompt, agent, PyPI, Python, app, web."
)

MODEL_SIZES = {
    "tiny": "Rất nhanh, kém chính xác (~75MB)",
    "base": "Nhanh (~145MB)",
    "small": "Cân bằng, khuyên dùng (~480MB)",
    "medium": "Chính xác hơn, chậm (~1.5GB)",
}


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    language: str
    duration: float
    segments: list[Segment] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Transcript":
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(d["language"], d["duration"], [Segment(**s) for s in d["segments"]])

    def between(self, start: float, end: float) -> list[Segment]:
        return [s for s in self.segments if s.end > start and s.start < end]

    def lines(self, start: float = 0.0, end: float | None = None) -> str:
        """Bản chép lời dạng "[mm:ss] câu", gửi cho AI."""
        end = self.duration if end is None else end
        return "\n".join(f"[{_mmss(s.start)}] {s.text}" for s in self.between(start, end))


def _mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def extract_audio(video: Path, out: Path, cancel: threading.Event | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)], cancel=cancel)
    return out


def _read_wav(path: Path):
    """Đọc WAV 16kHz mono 16-bit (do extract_audio tạo) thành mảng float32 cho Whisper.

    Đưa thẳng dữ liệu thay vì đường dẫn file: faster-whisper 1.2 tự đọc file bằng PyAV và bị lỗi với PyAV 19
    (tham số metadata_errors đã bị bỏ)."""
    import numpy as np

    with wave.open(str(path), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("File âm thanh phải là WAV 16kHz, 1 kênh, 16-bit.")
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def _load_model(size: str, device: str, models_dir: Path):
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # Windows không bật symlink: vẫn chạy, chỉ tốn thêm chỗ
    from faster_whisper import WhisperModel  # nhập muộn: thư viện nặng

    models_dir.mkdir(parents=True, exist_ok=True)
    if device == "cuda":
        try:
            return WhisperModel(size, device="cuda", compute_type="float16", download_root=str(models_dir))
        except Exception as e:  # thiếu thư viện CUDA/cuDNN: dùng CPU
            log.warning("Không chạy được Whisper trên GPU (%s), chuyển sang CPU", e)
    return WhisperModel(size, device="cpu", compute_type="int8", download_root=str(models_dir))


def transcribe(
    audio: Path, size: str, device: str, models_dir: Path, language: str | None = None,
    report: Callable[[float, str], None] | None = None, cancel: threading.Event | None = None,
) -> Transcript:
    report = report or (lambda f, m: None)
    report(0.0, f"Đang nạp model Whisper \"{size}\" (lần đầu sẽ tải về, có thể mất vài phút)")
    model = _load_model(size, device, models_dir)
    check_cancel(cancel)
    segments, info = model.transcribe(
        _read_wav(audio), language=language, vad_filter=True, beam_size=1, initial_prompt=TECH_TERMS
    )
    duration = info.duration or 0.0
    out = []
    for seg in segments:  # chạy dần, nên có thể báo tiến độ và hủy giữa chừng
        check_cancel(cancel)
        text = seg.text.strip()
        if text:
            out.append(Segment(round(seg.start, 2), round(seg.end, 2), text))
        if duration:
            report(min(1.0, seg.end / duration), f"Đang chép lời: {_mmss(seg.end)} / {_mmss(duration)}")
    log.info("Chép lời xong: %d câu, ngôn ngữ %s, %.0f giây", len(out), info.language, duration)
    return Transcript(info.language or "", round(duration, 2), out)
