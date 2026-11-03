import shutil

import pytest

from app.core.settings import VoiceSettings
from app.pipeline import tts
from app.pipeline.tts import TTSError, align_words, synthesize
from tests.fakes import ffmpeg

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="Cần ffmpeg")


def test_align_words_keeps_punctuation():
    b = [{"w": "Xin", "start": 0.0, "end": 0.2}, {"w": "chào", "start": 0.2, "end": 0.5}, {"w": "AI", "start": 0.6, "end": 0.9}]
    out = align_words("Xin chào, AI!", b)
    assert [w["w"] for w in out] == ["Xin", "chào,", "AI!"]
    assert out[1]["start"] == 0.2
    # Dịch vụ đọc khác chữ gốc (ví dụ số): dùng chữ của dịch vụ, không lệch các chữ sau
    out = align_words("Có 3 mẹo", [{"w": "Có", "start": 0, "end": 1}, {"w": "ba", "start": 1, "end": 2}, {"w": "mẹo", "start": 2, "end": 3}])
    assert [w["w"] for w in out] == ["Có", "ba", "mẹo"]


@needs_ffmpeg
def test_synthesize_edge_caches(tmp_path, monkeypatch):
    calls = []

    def fake_edge(text, voice, out, cancel):
        calls.append(text)
        ffmpeg("-f", "lavfi", "-i", "sine=duration=1.2", str(out))
        return [{"w": "Xin", "start": 0.1, "end": 0.5}, {"w": "chào", "start": 0.5, "end": 1.0}]

    monkeypatch.setattr(tts, "_edge_with_retry", fake_edge)
    speech = synthesize("Xin  chào.", tmp_path, VoiceSettings())
    assert speech.duration == pytest.approx(1.2, abs=0.1)
    assert [w["w"] for w in speech.words] == ["Xin", "chào."]
    again = synthesize("Xin chào.", tmp_path, VoiceSettings())  # khoảng trắng thừa không tính là câu khác
    assert again.audio == speech.audio and len(calls) == 1


@needs_ffmpeg
def test_synthesize_without_word_times_spreads_words(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "_edge_with_retry", lambda text, voice, out, cancel: ffmpeg("-f", "lavfi", "-i", "sine=duration=2", str(out)) or [])
    speech = synthesize("một hai ba bốn", tmp_path, VoiceSettings())
    assert len(speech.words) == 4 and speech.words[-1]["end"] == pytest.approx(speech.duration, abs=0.01)


def test_synthesize_errors(tmp_path):
    with pytest.raises(TTSError, match="trống"):
        synthesize("  ", tmp_path, VoiceSettings())
    with pytest.raises(TTSError, match="API key"):
        synthesize("xin chào", tmp_path, VoiceSettings("google", "vi-VN-Neural2-A"))
    with pytest.raises(TTSError, match="Không có dịch vụ"):
        synthesize("xin chào", tmp_path, VoiceSettings("khong-co", "x"))
    assert not list(tmp_path.glob("voice-*"))


def test_edge_retry_gives_clear_error(tmp_path, monkeypatch):
    async def always_fail(*args, **kwargs):
        raise RuntimeError("No audio was received")

    monkeypatch.setattr(tts, "_edge", always_fail)
    monkeypatch.setattr(tts, "EDGE_ATTEMPTS", ((0, True), (0, False)))
    monkeypatch.setattr(tts, "EDGE_MIN_GAP", 0)
    with pytest.raises(TTSError, match="không ổn định"):
        synthesize("xin chào", tmp_path, VoiceSettings())
