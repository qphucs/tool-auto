"""Điều phối các bước, chạy ở luồng nền (BackgroundTask).

Thư mục của mỗi dự án: <dữ liệu>/projects/<id>/
  audio.wav, transcript.json, cuts.json, frames/ (khung hình ứng viên)
  clips/<clip id>/ voice/ (giọng đọc), visuals/ (hình minh họa), cache/ (cảnh đã dựng), draft.mp4
Bản cuối nằm ở <dữ liệu>/outputs/.
"""

import json
import logging
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.ai.base import AIError, AIProvider
from app.ai.providers import create_provider
from app.core import secrets
from app.core.database import Database
from app.core.media import probe
from app.core.models import Clip, ClipStatus, Project, ProjectStatus
from app.core.settings import Settings
from app.editor.analyzer import detect_cuts
from app.editor.ffmpeg import Cancelled
from app.pipeline.assemble import scene_inputs
from app.pipeline.script import Script
from app.pipeline.transcribe import Transcript, extract_audio, transcribe
from app.pipeline.visuals import prepare_visuals
from app.pipeline.writer import Topic, find_topics, write_script
from app.render.clip import DRAFT_SIZE, FINAL_SIZE, render_clip, scene_seconds

log = logging.getLogger(__name__)

Report = Callable[[float, str], None]
GOOGLE_TTS_KEY = "tts.google.api_key"


def _span(report: Report, lo: float, hi: float) -> Report:
    """Đổi tiến độ 0-1 của một bước con thành lo-hi của cả việc."""
    return lambda f, m: report(lo + (hi - lo) * f, m)


def project_dir(settings: Settings, project_id: int) -> Path:
    return settings.projects_dir / str(project_id)


def clip_dir(settings: Settings, project_id: int, clip_id: int) -> Path:
    return project_dir(settings, project_id) / "clips" / str(clip_id)


def text_ai(settings: Settings) -> AIProvider:
    choice = settings.ai.text
    return create_provider(choice, settings.ai, secrets.get_secret(secrets.ai_key_name(choice.provider)))


def vision_ai(settings: Settings) -> AIProvider | None:
    choice = settings.ai.vision
    if choice.provider == "none":
        return None
    return create_provider(choice, settings.ai, secrets.get_secret(secrets.ai_key_name(choice.provider)))


def _load_cuts(pdir: Path) -> list[float]:
    path = pdir / "cuts.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def safe_name(text: str, limit: int = 60) -> str:
    """Tên file không dấu: "Mẹo dùng AI" -> "meo-dung-ai"."""
    text = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:limit] or "video"


# ----- phân tích video gốc -----

def analyze_project(settings: Settings, db: Database, project_id: int, report: Report,
                    cancel: threading.Event | None = None) -> int:
    """Chép lời, tìm kiến thức, viết kịch bản. Trả về số video ngắn được tạo."""
    with db.session() as s:
        project = s.get(Project, project_id)
        project.status, project.error = ProjectStatus.ANALYZING, ""
        s.commit()
        video = Path(project.source_path)
    pdir = project_dir(settings, project_id)
    pdir.mkdir(parents=True, exist_ok=True)
    try:
        if not video.is_file():
            raise FileNotFoundError(f"Không tìm thấy video gốc: {video}")
        ai = text_ai(settings)  # kiểm tra cài đặt AI trước khi mất thời gian chép lời

        transcript_path = pdir / "transcript.json"
        if transcript_path.exists():
            transcript = Transcript.load(transcript_path)
        else:
            report(0.01, "Đang tách âm thanh")
            audio = extract_audio(video, pdir / "audio.wav", cancel)
            w = settings.whisper
            transcript = transcribe(audio, w.model, w.device, settings.models_dir, None, _span(report, 0.03, 0.55), cancel)
            transcript.save(transcript_path)

        if not (pdir / "cuts.json").exists():
            report(0.56, "Đang tìm điểm chuyển cảnh")
            (pdir / "cuts.json").write_text(json.dumps(detect_cuts(video, cancel)), encoding="utf-8")

        report(0.6, "AI đang tìm các kiến thức trong video")
        topics = find_topics(ai, transcript, cancel)
        scripts = []
        for i, topic in enumerate(topics):
            report(0.65 + 0.35 * i / len(topics), f"AI đang viết kịch bản {i + 1}/{len(topics)}: {topic.title}")
            try:
                scripts.append(write_script(ai, transcript, topic, settings.brand.cta_enabled, cancel))
            except AIError as e:
                log.warning("Không viết được kịch bản \"%s\": %s", topic.title, e)
        if not scripts:
            raise AIError("AI không viết được kịch bản nào.")

        with db.session() as s:
            project = s.get(Project, project_id)
            project.clips.clear()  # phân tích lại thì thay toàn bộ kịch bản cũ
            for i, script in enumerate(scripts):
                project.clips.append(Clip(position=i, title=script.title, script_json=json.dumps(script.to_dict(), ensure_ascii=False)))
            project.status = ProjectStatus.READY
            project.language = transcript.language
            project.duration = transcript.duration
            s.commit()
        report(1.0, f"Xong: {len(scripts)} kịch bản chờ duyệt")
        return len(scripts)
    except Cancelled:
        _set_project(db, project_id, ProjectStatus.NEW, "")
        raise
    except Exception as e:
        _set_project(db, project_id, ProjectStatus.FAILED, str(e))
        raise


def _set_project(db: Database, project_id: int, status: ProjectStatus, error: str) -> None:
    with db.session() as s:
        project = s.get(Project, project_id)
        if project:
            project.status, project.error = status, error
            s.commit()


def rewrite_clip(settings: Settings, db: Database, clip_id: int, report: Report,
                 cancel: threading.Event | None = None) -> None:
    """Nhờ AI viết lại kịch bản của một video ngắn."""
    with db.session() as s:
        clip = s.get(Clip, clip_id)
        script = Script.from_dict(json.loads(clip.script_json))
        pdir = project_dir(settings, clip.project_id)
    report(0.1, "AI đang viết lại kịch bản")
    topic = Topic(script.title, script.start, script.end)
    new = write_script(text_ai(settings), Transcript.load(pdir / "transcript.json"), topic, settings.brand.cta_enabled, cancel)
    with db.session() as s:
        clip = s.get(Clip, clip_id)
        clip.script_json = json.dumps(new.to_dict(), ensure_ascii=False)
        clip.title, clip.status, clip.error = new.title, ClipStatus.SCRIPT, ""
        s.commit()
    report(1.0, "Đã viết lại kịch bản")


# ----- dựng video ngắn -----

@dataclass
class RenderOutcome:
    path: Path
    final: bool
    warnings: list[str] = field(default_factory=list)


def render_clip_job(settings: Settings, db: Database, clip_id: int, final: bool, report: Report,
                    cancel: threading.Event | None = None) -> RenderOutcome:
    with db.session() as s:
        clip = s.get(Clip, clip_id)
        project_id, title, music = clip.project_id, clip.title, clip.music_path
        script = Script.from_dict(json.loads(clip.script_json))
        video = Path(clip.project.source_path)
    pdir = project_dir(settings, project_id)
    cdir = clip_dir(settings, project_id, clip_id)
    try:
        problems = [p for p in script.problems() if "còn trống" in p or "cần" in p]
        if problems:
            raise ValueError("Kịch bản chưa đủ để dựng:\n" + "\n".join(problems))

        report(0.0, "Chuẩn bị hình minh họa")
        try:
            vision = vision_ai(settings)
        except AIError as e:
            vision = None
            log.warning("Không dùng được AI đọc ảnh: %s", e)
        warnings = prepare_visuals(script, video, _load_cuts(pdir), pdir / "frames", cdir / "visuals", vision,
                                   _span(report, 0.0, 0.1), cancel)
        with db.session() as s:  # lưu đường dẫn hình đã chuẩn bị để lần sau không phải làm lại
            s.get(Clip, clip_id).script_json = json.dumps(script.to_dict(), ensure_ascii=False)
            s.commit()

        key = secrets.get_secret(GOOGLE_TTS_KEY) if settings.voice.provider == "google" else ""
        scenes = scene_inputs(script, cdir / "voice", settings.voice, settings.brand, key, cancel, _span(report, 0.1, 0.3))

        if final:
            stamp = datetime.now().strftime("%Y%m%d-%H%M")
            out = settings.outputs_dir / f"{safe_name(title)}-{clip_id}-{stamp}.mp4"
        else:
            out = cdir / "draft.mp4"
        music_path = Path(music) if music and Path(music).is_file() else None
        render_clip(scenes, out, cdir / "cache", FINAL_SIZE if final else DRAFT_SIZE, settings.brand, music_path,
                    _span(report, 0.3, 1.0), cancel)
        # Độ dài từng cảnh, để trang Xem nháp tách ảnh thu nhỏ đúng từng cảnh
        timing = {"video": str(out), "types": [s.type for s in scenes], "durations": [scene_seconds(s) for s in scenes]}
        (cdir / ("final.json" if final else "draft.json")).write_text(json.dumps(timing), encoding="utf-8")

        with db.session() as s:
            clip = s.get(Clip, clip_id)
            if final:
                clip.final_path, clip.status = str(out), ClipStatus.FINAL
            else:
                clip.draft_path = str(out)
                if clip.status in (ClipStatus.SCRIPT, ClipStatus.FAILED):
                    clip.status = ClipStatus.DRAFT
            clip.error = ""
            s.commit()
        return RenderOutcome(out, final, warnings)
    except Cancelled:
        raise
    except Exception as e:
        with db.session() as s:
            clip = s.get(Clip, clip_id)
            clip.error = str(e)
            s.commit()
        raise


def source_info(path: Path) -> tuple[float | None, str]:
    info = probe(path)
    return info.duration, info.describe()
