"""Chạy trọn luồng với video thật nhỏ, AI giả, giọng đọc giả: phân tích → kịch bản → nháp → bản cuối."""

import json
import shutil

import pytest

from app.automation.browser import find_chrome
from app.core.media import probe
from app.core.models import Clip, ClipStatus, Project, ProjectStatus
from app.core.settings import Settings
from app.pipeline import assemble, runner
from app.pipeline.script import Script
from app.pipeline.transcribe import Segment, Transcript
from tests.fakes import FakeAI, fake_synthesize, good_script, make_video

pytestmark = pytest.mark.skipif(find_chrome() is None or shutil.which("ffmpeg") is None, reason="Cần Chrome và FFmpeg")


@pytest.fixture
def setup(tmp_path, db, monkeypatch):
    settings = Settings(data_dir=str(tmp_path / "data"))
    video = make_video(tmp_path / "goc.mp4")
    with db.session() as s:
        project = Project(name="goc", source_path=str(video))
        s.add(project)
        s.commit()
        project_id = project.id

    fake_transcript = Transcript("en", 12.0, [Segment(0, 5, "First tip about AI."), Segment(5, 12, "Second tip.")])
    monkeypatch.setattr(runner, "transcribe", lambda *a, **k: fake_transcript)
    monkeypatch.setattr(assemble, "synthesize", fake_synthesize)
    return settings, project_id


def test_full_flow(setup, db, monkeypatch):
    settings, project_id = setup
    ai = FakeAI([
        {"topics": [{"title": "Mẹo một", "start": "00:00", "end": "00:06"}, {"title": "Mẹo hai", "start": 6, "end": 12}]},
        good_script("Mẹo một", "00:03"), good_script("Mẹo hai", "00:08"),
    ])
    monkeypatch.setattr(runner, "text_ai", lambda s: ai)
    progress = []
    assert runner.analyze_project(settings, db, project_id, lambda f, m: progress.append(f)) == 2
    assert progress[-1] == 1.0

    pdir = runner.project_dir(settings, project_id)
    assert (pdir / "transcript.json").exists() and (pdir / "cuts.json").exists() and (pdir / "audio.wav").exists()
    with db.session() as s:
        project = s.get(Project, project_id)
        assert project.status == ProjectStatus.READY and project.language == "en"
        clips = [(c.id, c.title, c.status) for c in project.clips]
    assert [c[1] for c in clips] == ["Mẹo một", "Mẹo hai"]
    assert all(c[2] == ClipStatus.SCRIPT for c in clips)
    clip_id = clips[0][0]

    # Nháp: tách khung hình cho cảnh ảnh chụp, có giọng đọc, có cảnh kêu gọi do tool thêm
    outcome = runner.render_clip_job(settings, db, clip_id, False, lambda f, m: None)
    info = probe(outcome.path)
    assert (info.width, info.height) == (540, 960) and info.has_audio
    cdir = runner.clip_dir(settings, project_id, clip_id)
    timing = json.loads((cdir / "draft.json").read_text(encoding="utf-8"))
    assert timing["types"][-1] == "cta" and len(timing["types"]) == 6
    assert info.duration == pytest.approx(sum(timing["durations"]), abs=0.3)
    with db.session() as s:
        clip = s.get(Clip, clip_id)
        assert clip.status == ClipStatus.DRAFT and clip.draft_path == str(outcome.path)
        shot = Script.from_dict(json.loads(clip.script_json)).scenes[2]
    assert shot.visual.path and shot.visual.time == 3.0  # đường dẫn ảnh được lưu lại cho lần sau

    # Dựng lại nháp không đổi gì: không phải dựng lại cảnh nào
    cached = sorted(p.name for p in (cdir / "cache").glob("scene-*.mp4"))
    runner.render_clip_job(settings, db, clip_id, False, lambda f, m: None)
    assert sorted(p.name for p in (cdir / "cache").glob("scene-*.mp4")) == cached

    # Bản cuối 1080x1920 vào thư mục outputs
    final = runner.render_clip_job(settings, db, clip_id, True, lambda f, m: None)
    assert final.path.parent == settings.outputs_dir
    assert (probe(final.path).width, probe(final.path).height) == (1080, 1920)
    with db.session() as s:
        assert s.get(Clip, clip_id).status == ClipStatus.FINAL


def test_analyze_failure_is_recorded(setup, db, monkeypatch):
    settings, project_id = setup
    monkeypatch.setattr(runner, "text_ai", lambda s: FakeAI(["không phải json"]))
    with pytest.raises(Exception):
        runner.analyze_project(settings, db, project_id, lambda f, m: None)
    with db.session() as s:
        project = s.get(Project, project_id)
        assert project.status == ProjectStatus.FAILED and "JSON" in project.error


def test_render_refuses_incomplete_script(setup, db):
    settings, project_id = setup
    with db.session() as s:
        clip = Clip(project_id=project_id, title="x", script_json=json.dumps({"title": "x", "scenes": [{"type": "hook"}]}))
        s.add(clip)
        s.commit()
        clip_id = clip.id
    with pytest.raises(ValueError, match="chưa đủ"):
        runner.render_clip_job(settings, db, clip_id, False, lambda f, m: None)
    with db.session() as s:
        assert "chưa đủ" in s.get(Clip, clip_id).error


def test_safe_name():
    assert runner.safe_name("Mẹo dùng AI: Đỉnh cao!") == "meo-dung-ai-dinh-cao"
    assert runner.safe_name("???") == "video"
