import json

from PySide6.QtWidgets import QMessageBox

from app.core.models import Clip, Project
from app.core.settings import load_settings
from app.pipeline.script import Script
from app.render.sample import sample_script
from app.ui.main_window import PAGES, MainWindow
from app.ui.pages.projects import ProjectsPage
from app.ui.pages.scripts import ScriptsPage
from app.ui.pages.settings_page import SettingsPage


def _clip(ctx) -> tuple[int, int]:
    with ctx.db.session() as s:
        project = Project(name="Video gốc", source_path="E:/khong-co.mp4")
        project.clips.append(Clip(position=0, title="Mẹo", script_json=json.dumps(sample_script().to_dict(), ensure_ascii=False)))
        s.add(project)
        s.commit()
        return project.id, project.clips[0].id


def _script(ctx, clip_id) -> Script:
    with ctx.db.session() as s:
        return Script.from_dict(json.loads(s.get(Clip, clip_id).script_json))


def test_every_page_opens(ctx):
    _clip(ctx)
    window = MainWindow(ctx)
    assert window.sidebar.count() == len(PAGES)
    for row in range(window.sidebar.count()):
        window.sidebar.setCurrentRow(row)
        assert window.stack.currentIndex() == row
    window.close()


def test_settings_page_saves(ctx, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr("app.ui.pages.settings_page.secrets.set_secret", lambda *a: None)
    window = MainWindow(ctx)
    page = window.page(SettingsPage)
    page.text_ai.provider.setCurrentIndex(page.text_ai.provider.findData("gemini"))
    page.text_ai.model.setEditText("gemini-test")
    page.voice_rate.setValue(15)
    page.voice_name.setCurrentIndex(page.voice_name.findData("vi-VN-NamMinhNeural"))
    page._save()

    assert page.vision_ai.provider.currentData() == "none"  # mặc định không dùng AI đọc ảnh

    saved = load_settings()
    assert (saved.ai.text.provider, saved.ai.text.model) == ("gemini", "gemini-test")
    assert saved.ai.vision.provider == "none"
    assert saved.voice.rate == 15 and saved.voice.voice == "vi-VN-NamMinhNeural"
    window.close()


def test_projects_page_adds_only_videos(ctx, tmp_path):
    video = tmp_path / "bai-giang.mp4"
    video.write_bytes(b"x")
    (tmp_path / "ghi-chu.txt").write_text("x")
    window = MainWindow(ctx)
    page = window.page(ProjectsPage)
    assert page.add_videos([video, tmp_path / "ghi-chu.txt", tmp_path / "missing.mp4"]) == 1
    assert page.table.rowCount() == 1
    window.close()


def test_scripts_page_edit_move_save(ctx):
    project_id, clip_id = _clip(ctx)
    window = MainWindow(ctx)
    window.open_scripts(project_id=project_id)
    page = window.page(ScriptsPage)
    assert page.scenes.count() == len(sample_script().scenes)

    # Sửa tiêu đề cảnh 2 rồi chuyển sang cảnh khác: nội dung vừa sửa phải được giữ
    page.scenes.setCurrentRow(1)
    page.editor._widgets["line1"][1].setText("Tiêu đề mới")
    page.scenes.setCurrentRow(0)
    # Đưa cảnh 1 xuống dưới: cảnh 2 (đã sửa) lên đầu, không ghi nhầm nội dung
    page._move_scene(1)
    page.save()

    script = _script(ctx, clip_id)
    assert script.scenes[0].data["line1"] == "Tiêu đề mới"
    assert script.scenes[1].type == "hook"
    assert [s.type for s in script.scenes[2:]] == [s.type for s in sample_script().scenes[2:]]
    window.close()


def test_scripts_page_loading_keeps_visual_path(ctx, tmp_path):
    project_id, clip_id = _clip(ctx)
    image = tmp_path / "anh.png"
    image.write_bytes(b"x")
    with ctx.db.session() as s:
        clip = s.get(Clip, clip_id)
        data = json.loads(clip.script_json)
        shot = next(sc for sc in data["scenes"] if sc["type"] == "screenshot")
        shot["visual"] = {"kind": "source", "time": 12.5, "url": "", "path": str(image)}
        clip.script_json = json.dumps(data, ensure_ascii=False)
        s.commit()
    window = MainWindow(ctx)
    window.open_scripts(clip_id=clip_id)
    page = window.page(ScriptsPage)
    for row in range(page.scenes.count()):  # đi qua mọi cảnh
        page.scenes.setCurrentRow(row)
    page.save()
    shot = next(s for s in _script(ctx, clip_id).scenes if s.type == "screenshot")
    assert shot.visual.path == str(image) and shot.visual.time == 12.5
    window.close()
