"""Chuyển kịch bản thành các cảnh sẵn sàng để dựng: làm gọn dữ liệu, tạo giọng đọc, tính độ dài, phụ đề."""

import threading
from pathlib import Path
from typing import Callable

from app.core.settings import BrandSettings, VoiceSettings
from app.pipeline.script import Scene, Script
from app.pipeline.tts import synthesize
from app.render.clip import AUDIO_LEAD, SceneInput
from app.render.page import even_captions
from app.render.scenes import clean_scene

MIN_SCENE = 3.0
TAIL = 0.6  # giữ cảnh thêm một chút sau khi đọc xong
WORDS_PER_SECOND = 2.6  # ước tính khi không có giọng đọc


def cta_scene(brand: BrandSettings) -> Scene:
    data = {"question": brand.cta_question, "hint": brand.cta_hint, "button": brand.cta_button}
    narration = " ".join(p.strip() for p in (brand.cta_question, brand.cta_hint) if p.strip())
    return Scene("cta", narration, data)


def with_cta(script: Script, brand: BrandSettings) -> list[Scene]:
    scenes = [s for s in script.scenes if s.type != "cta"]
    if brand.cta_enabled and brand.cta_question.strip():
        scenes.append(cta_scene(brand))
    return scenes


def scene_inputs(
    script: Script, voice_dir: Path, voice: VoiceSettings | None, brand: BrandSettings,
    api_key: str = "", cancel: threading.Event | None = None, report: Callable[[float, str], None] | None = None,
) -> list[SceneInput]:
    """voice=None: không tạo giọng đọc, độ dài cảnh ước tính theo số chữ."""
    scenes = with_cta(script, brand)
    out = []
    for i, s in enumerate(scenes):
        if report:
            report(i / len(scenes), f"Giọng đọc cảnh {i + 1}/{len(scenes)}")
        data, _ = clean_scene(s.type, s.data)
        if s.type == "screenshot" and s.visual.path and Path(s.visual.path).is_file():
            data["image"] = s.visual.path
        text = s.narration.strip()
        audio = None
        if text and voice is not None:
            speech = synthesize(text, voice_dir, voice, api_key, cancel)
            audio = speech.audio
            duration = max(MIN_SCENE, speech.duration + AUDIO_LEAD + TAIL)
            words = speech.words
        else:
            duration = max(MIN_SCENE, len(text.split()) / WORDS_PER_SECOND + AUDIO_LEAD + TAIL)
            words = even_captions(text, 0.0, duration - AUDIO_LEAD - TAIL)
        captions = [
            {"w": w["w"], "start": round(w["start"] + AUDIO_LEAD, 3), "end": round(w["end"] + AUDIO_LEAD, 3)} for w in words
        ]
        out.append(SceneInput(s.type, data, round(duration, 3), captions, audio))
    if report:
        report(1.0, "Đã có giọng đọc")
    return out
