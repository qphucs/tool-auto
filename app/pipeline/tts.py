"""Giọng đọc AI (TTS) kèm mốc thời gian từng từ để làm phụ đề tô sáng.

- edge: Edge TTS, miễn phí, cần mạng, có mốc thời gian từng từ thật. Thư viện không chính thức.
- google: Google Cloud Text-to-Speech, cần API key, có hạn mức miễn phí hàng tháng.
- windows: giọng có sẵn trong Windows, offline (cần cài gói giọng tiếng Việt của Windows).
Hai dịch vụ sau không trả mốc từng từ nên thời gian được chia theo độ dài chữ.
"""

import asyncio
import base64
import hashlib
import json
import logging
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.media import probe
from app.core.settings import VoiceSettings
from app.editor.ffmpeg import check_cancel
from app.render.page import even_captions

log = logging.getLogger(__name__)

PROVIDERS = {
    "edge": "Edge TTS (miễn phí, cần mạng)",
    "google": "Google Cloud TTS (cần API key)",
    "windows": "Giọng Windows (offline)",
}
VOICES = {
    "edge": [("vi-VN-HoaiMyNeural", "Hoài My (nữ)"), ("vi-VN-NamMinhNeural", "Nam Minh (nam)")],
    "google": [
        ("vi-VN-Neural2-A", "Neural2 A (nữ)"),
        ("vi-VN-Neural2-D", "Neural2 D (nam)"),
        ("vi-VN-Wavenet-A", "Wavenet A (nữ)"),
        ("vi-VN-Wavenet-B", "Wavenet B (nam)"),
    ],
    "windows": [],  # đọc từ máy, xem windows_voices()
}
GOOGLE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_TICKS = 10_000_000  # Edge TTS tính thời gian theo đơn vị 100 nano-giây


class TTSError(Exception):
    pass


@dataclass
class Speech:
    audio: Path
    duration: float
    words: list[dict]  # [{w, start, end}] tính từ đầu file âm thanh


def _norm(token: str) -> str:
    return re.sub(r"[^\w]", "", token.lower())


def align_words(text: str, boundaries: list[dict]) -> list[dict]:
    """Ghép mốc thời gian của dịch vụ với chữ gốc (giữ dấu câu và chữ hoa để hiển thị)."""
    tokens = text.split()
    out, j = [], 0
    for b in boundaries:
        word = b["w"]
        # Tìm chữ gốc tiếp theo khớp với từ được đọc; nếu không khớp thì dùng nguyên từ của dịch vụ
        for k in range(j, min(j + 3, len(tokens))):
            if _norm(tokens[k]) == _norm(word):
                word = tokens[k]
                j = k + 1
                break
        out.append({"w": word, "start": b["start"], "end": b["end"]})
    return out


async def _edge(text: str, voice: str, rate: int, out: Path, word_boundary: bool = True) -> list[dict]:
    """Trả về mốc thời gian từng từ (rỗng nếu đọc ở chế độ theo câu)."""
    import edge_tts  # nhập muộn: chỉ cần khi dùng Edge

    boundary = "WordBoundary" if word_boundary else "SentenceBoundary"
    communicate = edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", boundary=boundary)
    boundaries = []
    with out.open("wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / _TICKS
                boundaries.append({"w": chunk["text"], "start": round(start, 3), "end": round(start + chunk["duration"] / _TICKS, 3)})
    return boundaries


# Edge thỉnh thoảng trả "No audio was received" một cách ngẫu nhiên (đo được ~40% số yêu cầu
# vào lúc dịch vụ kém ổn định), không phụ thuộc câu chữ. Thử lại nhiều lần, xen kẽ chế độ
# có mốc từng từ và chế độ theo câu, chờ tăng dần. (giây chờ trước lần thử, có mốc từng từ không)
EDGE_ATTEMPTS = ((0, True), (1, True), (1, False), (2, True), (3, False), (5, True), (8, False))
EDGE_MIN_GAP = 0.6  # giãn cách giữa hai yêu cầu
_edge_last = 0.0


def _edge_with_retry(text: str, voice: VoiceSettings, out: Path, cancel: threading.Event | None) -> list[dict]:
    global _edge_last
    last_error: Exception | None = None
    for attempt, (wait, word_boundary) in enumerate(EDGE_ATTEMPTS, 1):
        if attempt > 1:
            log.warning("Edge TTS chưa trả âm thanh, thử lại lần %d/%d", attempt, len(EDGE_ATTEMPTS))
        deadline = time.monotonic() + max(wait, EDGE_MIN_GAP - (time.monotonic() - _edge_last))
        while time.monotonic() < deadline:
            check_cancel(cancel)
            time.sleep(0.1)
        try:
            boundaries = asyncio.run(_edge(text, voice.voice, voice.rate, out, word_boundary))
            if out.stat().st_size > 0:
                return boundaries
        except Exception as e:
            last_error = e
        finally:
            _edge_last = time.monotonic()
    raise TTSError(
        f"Edge TTS không trả âm thanh sau {len(EDGE_ATTEMPTS)} lần thử ({last_error}). "
        "Dịch vụ đang không ổn định, hãy thử lại sau ít phút hoặc đổi dịch vụ giọng đọc trong Cài đặt."
    )


def _google(text: str, voice: str, rate: int, out: Path, api_key: str) -> None:
    if not api_key:
        raise TTSError("Chưa có API key của Google Cloud TTS (trang Cài đặt).")
    body = {
        "input": {"text": text},
        "voice": {"languageCode": voice[:5], "name": voice},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": max(0.5, min(2.0, 1 + rate / 100))},
    }
    try:
        resp = httpx.post(GOOGLE_URL, params={"key": api_key}, json=body, timeout=60)
    except httpx.HTTPError as e:
        raise TTSError(f"Không kết nối được Google TTS: {e}") from e
    if resp.status_code != 200:
        raise TTSError(f"Google TTS báo lỗi {resp.status_code}: {resp.text[:300]}")
    out.write_bytes(base64.b64decode(resp.json()["audioContent"]))


_PS_SPEAK = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($env:TTS_VOICE) { $s.SelectVoice($env:TTS_VOICE) }
$s.Rate = [int]$env:TTS_RATE
$s.SetOutputToWaveFile($env:TTS_OUT)
$s.Speak([IO.File]::ReadAllText($env:TTS_TEXT, [Text.Encoding]::UTF8))
$s.Dispose()
"""

_PS_VOICES = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }
"""


def _powershell(script: str, env: dict | None = None) -> str:
    import os

    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        env={**os.environ, **(env or {})}, creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise TTSError(f"Giọng Windows báo lỗi: {proc.stderr.strip()[-300:]}")
    return proc.stdout


def windows_voices() -> list[tuple[str, str]]:
    """[(tên giọng, nhãn)] các giọng Windows đã cài, giọng tiếng Việt xếp trước."""
    try:
        lines = _powershell(_PS_VOICES).splitlines()
    except (TTSError, OSError, subprocess.SubprocessError):
        return []
    voices = []
    for line in lines:
        name, _, culture = line.strip().partition("|")
        if name:
            voices.append((name, f"{name} ({culture})"))
    return sorted(voices, key=lambda v: not v[1].endswith("(vi-VN)"))


def _windows(text: str, voice: str, rate: int, out: Path) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        text_file = f.name
    try:
        _powershell(_PS_SPEAK, {"TTS_VOICE": voice, "TTS_RATE": str(max(-10, min(10, round(rate / 10)))),
                                "TTS_OUT": str(out), "TTS_TEXT": text_file})
    finally:
        Path(text_file).unlink(missing_ok=True)


def speech_key(text: str, voice: VoiceSettings) -> str:
    return hashlib.sha1(json.dumps([voice.provider, voice.voice, voice.rate, text], ensure_ascii=False).encode()).hexdigest()[:16]


def synthesize(text: str, out_dir: Path, voice: VoiceSettings, api_key: str = "",
               cancel: threading.Event | None = None) -> Speech:
    """Đọc `text` thành file âm thanh trong out_dir. Câu đã đọc trước đó được dùng lại."""
    text = " ".join(text.split())
    if not text:
        raise TTSError("Lời đọc còn trống.")
    check_cancel(cancel)
    out_dir.mkdir(parents=True, exist_ok=True)
    key = speech_key(text, voice)
    ext = "wav" if voice.provider == "windows" else "mp3"
    audio = out_dir / f"voice-{key}.{ext}"
    meta = out_dir / f"voice-{key}.json"
    if audio.exists() and meta.exists():
        cached = json.loads(meta.read_text(encoding="utf-8"))
        return Speech(audio, cached["duration"], cached["words"])

    boundaries: list[dict] = []
    try:
        if voice.provider == "edge":
            boundaries = _edge_with_retry(text, voice, audio, cancel)
        elif voice.provider == "google":
            _google(text, voice.voice, voice.rate, audio, api_key)
        elif voice.provider == "windows":
            _windows(text, voice.voice, voice.rate, audio)
        else:
            raise TTSError(f"Không có dịch vụ giọng đọc: {voice.provider}")
    except TTSError:
        audio.unlink(missing_ok=True)
        raise
    except Exception as e:  # lỗi mạng, dịch vụ đổi API...
        audio.unlink(missing_ok=True)
        raise TTSError(f"Không tạo được giọng đọc ({voice.provider}): {e}") from e

    duration = probe(audio).duration
    if not duration:
        audio.unlink(missing_ok=True)
        raise TTSError("File giọng đọc bị lỗi.")
    words = align_words(text, boundaries) if boundaries else even_captions(text, 0.0, duration)
    meta.write_text(json.dumps({"duration": duration, "words": words}, ensure_ascii=False), encoding="utf-8")
    return Speech(audio, duration, words)
