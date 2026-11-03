import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from app.core.context import AppContext
from app.core.models import CLIP_STATUS_LABELS, Clip, ClipStatus, Project
from app.editor.ffmpeg import Cancelled
from app.pipeline import runner
from app.pipeline.assemble import WORDS_PER_SECOND
from app.pipeline.script import Scene, Script
from app.render.scenes import SCENES
from app.ui.pages.base import Page
from app.ui.scene_editor import SceneEditor


def scene_caption(i: int, scene: Scene) -> str:
    d = scene.data
    text = d.get("line1") or d.get("title") or d.get("question") or d.get("label") or scene.narration[:30]
    warn = " ⚠" if scene.problems() else ""
    return f"{i + 1}. {SCENES[scene.type].label}: {text}{warn}"


class ScriptsPage(Page):
    title = "Kịch bản"
    subtitle = "Duyệt và sửa kịch bản AI viết. Mỗi video ngắn gồm nhiều cảnh; chọn một cảnh để sửa chữ, lời đọc, hình."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self._clip_id: int | None = None
        self._script: Script | None = None
        self._scene_index: int | None = None
        self._dirty = False

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Video gốc:"))
        self.project = QComboBox()
        self.project.setMinimumWidth(260)
        bar.addWidget(self.project)
        bar.addStretch(1)
        self.rewrite_btn = QPushButton("Viết lại bằng AI")
        self.skip_btn = QPushButton("Bỏ video này")
        self.save_btn = QPushButton("Lưu")
        self.draft_btn = QPushButton("Duyệt và dựng nháp")
        self.draft_btn.setObjectName("primary")
        for b in (self.rewrite_btn, self.skip_btn, self.save_btn, self.draft_btn):
            bar.addWidget(b)
        self.body.addLayout(bar)

        self.clips = QListWidget()
        self.clips.setMinimumWidth(200)

        middle = QWidget()
        mid = QVBoxLayout(middle)
        mid.setContentsMargins(0, 0, 0, 0)
        self.clip_title = QLineEdit()
        self.clip_title.setPlaceholderText("Tiêu đề video")
        self.clip_info = QLabel()
        self.clip_info.setObjectName("muted")
        self.clip_info.setWordWrap(True)
        self.scenes = QListWidget()
        scene_bar = QHBoxLayout()
        self.add_scene_btn = QPushButton("+ Cảnh")
        self.up_btn = QPushButton("↑")
        self.down_btn = QPushButton("↓")
        self.del_scene_btn = QPushButton("Xóa cảnh")
        for b in (self.add_scene_btn, self.up_btn, self.down_btn, self.del_scene_btn):
            scene_bar.addWidget(b)
        menu = QMenu(self)
        for key, spec in SCENES.items():
            if key != "cta":
                menu.addAction(spec.label, lambda k=key: self._add_scene(k))
        self.add_scene_btn.setMenu(menu)
        mid.addWidget(self.clip_title)
        mid.addWidget(self.clip_info)
        mid.addWidget(self.scenes, 1)
        mid.addLayout(scene_bar)

        self.editor = SceneEditor()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self.editor)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(scroll, 1)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setStyleSheet("color: #b91c1c;")
        rl.addWidget(self.problems)

        splitter = QSplitter()
        splitter.addWidget(self.clips)
        splitter.addWidget(middle)
        splitter.addWidget(right)
        splitter.setSizes([210, 260, 520])
        self.body.addWidget(splitter, 1)

        self.project.activated.connect(lambda: self._load_clips())
        self.clips.currentRowChanged.connect(self._on_clip_changed)
        self.scenes.currentRowChanged.connect(self._on_scene_changed)
        self.editor.changed.connect(self._on_edit)
        self.clip_title.textEdited.connect(self._on_edit)
        self.up_btn.clicked.connect(lambda: self._move_scene(-1))
        self.down_btn.clicked.connect(lambda: self._move_scene(1))
        self.del_scene_btn.clicked.connect(self._delete_scene)
        self.save_btn.clicked.connect(self.save)
        self.rewrite_btn.clicked.connect(self._rewrite)
        self.skip_btn.clicked.connect(self._toggle_skip)
        self.draft_btn.clicked.connect(self._render_draft)
        ctx.media.finished.connect(self._on_finished)
        ctx.media.started.connect(lambda _: self._update_buttons())
        self._update_buttons()

    # ----- điều hướng -----

    def on_show(self) -> None:
        current = self.project.currentData()
        self.project.blockSignals(True)
        self.project.clear()
        with self.ctx.db.session() as s:
            for p in s.scalars(select(Project).order_by(Project.created_at.desc())):
                if p.clips:
                    self.project.addItem(f"{p.name} ({len(p.clips)} video)", p.id)
        self.project.blockSignals(False)
        if self.project.count():
            self.project.setCurrentIndex(max(self.project.findData(current), 0))
        self._load_clips(keep=self._clip_id)

    def open(self, project_id: int | None = None, clip_id: int | None = None, scene_index: int | None = None) -> None:
        self.on_show()
        if project_id is None and clip_id is not None:
            with self.ctx.db.session() as s:
                project_id = s.get(Clip, clip_id).project_id
        if project_id is not None:
            self.project.setCurrentIndex(max(self.project.findData(project_id), 0))
            self._load_clips(keep=clip_id)
        if scene_index is not None and 0 <= scene_index < self.scenes.count():
            self.scenes.setCurrentRow(scene_index)

    def _load_clips(self, keep: int | None = None) -> None:
        self._autosave()
        self.clips.blockSignals(True)
        self.clips.clear()
        project_id = self.project.currentData()
        with self.ctx.db.session() as s:
            clips = s.scalars(select(Clip).where(Clip.project_id == project_id).order_by(Clip.position)).all() if project_id else []
            for c in clips:
                item = QListWidgetItem(f"{c.position + 1}. {c.title}\n    {CLIP_STATUS_LABELS[c.status]}")
                item.setData(Qt.ItemDataRole.UserRole, c.id)
                if c.status == ClipStatus.SKIPPED:
                    item.setForeground(Qt.GlobalColor.gray)
                self.clips.addItem(item)
        self.clips.blockSignals(False)
        ids = [self.clips.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.clips.count())]
        row = ids.index(keep) if keep in ids else (0 if ids else -1)
        self._clip_id = None
        self.clips.setCurrentRow(row)
        if row < 0:
            self._show_clip(None)

    def _on_clip_changed(self, row: int) -> None:
        self._autosave()
        item = self.clips.item(row) if row >= 0 else None
        self._show_clip(item.data(Qt.ItemDataRole.UserRole) if item else None)

    def _show_clip(self, clip_id: int | None) -> None:
        self._clip_id = clip_id
        self._script = None
        if clip_id is not None:
            with self.ctx.db.session() as s:
                clip = s.get(Clip, clip_id)
                self._script = Script.from_dict(json.loads(clip.script_json))
                self._clip_status = clip.status
                self._clip_error = clip.error
        self._dirty = False
        self._refresh_scene_list(select_row=0)
        self._update_buttons()

    def _refresh_scene_list(self, select_row: int | None = None) -> None:
        current = self.scenes.currentRow() if select_row is None else select_row
        # Danh sách cảnh có thể vừa đổi thứ tự: không được ghi ô sửa vào vị trí cũ
        self._scene_index = None
        self.scenes.blockSignals(True)
        self.scenes.clear()
        script = self._script
        self.clip_title.setText(script.title if script else "")
        self.clip_title.setEnabled(script is not None)
        if script:
            for i, sc in enumerate(script.scenes):
                self.scenes.addItem(scene_caption(i, sc))
            words = script.narration_words()
            cta = " (+ cảnh kêu gọi cuối video)" if self.ctx.settings.brand.cta_enabled else ""
            err = f"\nLỗi lần dựng trước: {self._clip_error}" if self._clip_error else ""
            self.clip_info.setText(
                f"{len(script.scenes)} cảnh{cta} · {words} chữ lời đọc · khoảng {words / WORDS_PER_SECOND:.0f} giây{err}"
            )
        else:
            self.clip_info.setText("Chưa có kịch bản. Phân tích một video gốc ở trang Dự án.")
        self.scenes.blockSignals(False)
        if script and script.scenes:
            self.scenes.setCurrentRow(min(max(current, 0), len(script.scenes) - 1))  # gọi _on_scene_changed
        else:
            self.editor.set_scene(None)
        self._update_problems()

    def _on_scene_changed(self, row: int) -> None:
        self._pull_editor()
        self._scene_index = row if self._script and 0 <= row < len(self._script.scenes) else None
        self.editor.set_scene(self._script.scenes[row] if self._scene_index is not None else None)
        self._update_buttons()

    # ----- sửa -----

    def _pull_editor(self) -> None:
        """Ghi nội dung đang sửa trong ô sửa cảnh vào kịch bản (trong bộ nhớ)."""
        if self._script is None or self._scene_index is None:
            return
        scene = self.editor.scene()
        if scene is not None and self._scene_index < len(self._script.scenes):
            self._script.scenes[self._scene_index] = scene

    def _on_edit(self) -> None:
        self._dirty = True
        self._pull_editor()
        if self._script is not None:
            self._script.title = self.clip_title.text().strip() or self._script.title
        if self._scene_index is not None and self._script:
            item = self.scenes.item(self._scene_index)
            if item:
                item.setText(scene_caption(self._scene_index, self._script.scenes[self._scene_index]))
        self._update_problems()

    def _update_problems(self) -> None:
        self.problems.setText("\n".join(self._script.problems()) if self._script else "")

    def _add_scene(self, scene_type: str) -> None:
        if self._script is None:
            return
        self._pull_editor()
        at = (self._scene_index + 1) if self._scene_index is not None else len(self._script.scenes)
        self._script.scenes.insert(at, Scene(scene_type))
        self._dirty = True
        self._refresh_scene_list(select_row=at)

    def _move_scene(self, step: int) -> None:
        i = self._scene_index
        if self._script is None or i is None or not 0 <= i + step < len(self._script.scenes):
            return
        self._pull_editor()
        s = self._script.scenes
        s[i], s[i + step] = s[i + step], s[i]
        self._dirty = True
        self._refresh_scene_list(select_row=i + step)

    def _delete_scene(self) -> None:
        if self._script is None or self._scene_index is None:
            return
        del self._script.scenes[self._scene_index]
        self._scene_index = None
        self._dirty = True
        self._refresh_scene_list()

    def save(self) -> bool:
        if self._clip_id is None or self._script is None:
            return False
        self._pull_editor()
        self._script.title = self.clip_title.text().strip() or self._script.title
        with self.ctx.db.session() as s:
            clip = s.get(Clip, self._clip_id)
            clip.script_json = json.dumps(self._script.to_dict(), ensure_ascii=False)
            clip.title = self._script.title
            s.commit()
        self._dirty = False
        item = self.clips.currentItem()
        if item:
            item.setText(f"{self.clips.currentRow() + 1}. {self._script.title}\n    {CLIP_STATUS_LABELS[self._clip_status]}")
        self.window().statusBar().showMessage("Đã lưu kịch bản.", 4000)
        return True

    def _autosave(self) -> None:
        if self._dirty:
            self.save()

    # ----- việc nền -----

    def _update_buttons(self) -> None:
        has_clip = self._clip_id is not None
        busy = self.ctx.media.running
        for b in (self.rewrite_btn, self.draft_btn):
            b.setEnabled(has_clip and not busy)
        self.save_btn.setEnabled(has_clip)
        self.skip_btn.setEnabled(has_clip)
        skipped = has_clip and getattr(self, "_clip_status", None) == ClipStatus.SKIPPED
        self.skip_btn.setText("Dùng lại video này" if skipped else "Bỏ video này")
        has_scene = self._scene_index is not None
        for b in (self.up_btn, self.down_btn, self.del_scene_btn):
            b.setEnabled(has_scene)
        self.add_scene_btn.setEnabled(has_clip)

    def _toggle_skip(self) -> None:
        with self.ctx.db.session() as s:
            clip = s.get(Clip, self._clip_id)
            clip.status = ClipStatus.SCRIPT if clip.status == ClipStatus.SKIPPED else ClipStatus.SKIPPED
            s.commit()
        self._load_clips(keep=self._clip_id)

    def _rewrite(self) -> None:
        answer = QMessageBox.question(self, "Viết lại", "AI sẽ viết lại toàn bộ kịch bản này, các chỗ bạn đã sửa sẽ mất.\n\nTiếp tục?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        clip_id, settings, db = self._clip_id, self.ctx.settings, self.ctx.db
        self.ctx.media.start("rewrite", lambda report, cancel: runner.rewrite_clip(settings, db, clip_id, report, cancel))

    def _render_draft(self) -> None:
        self.save()
        if self._script and [p for p in self._script.problems() if "còn trống" in p or "cần" in p]:
            QMessageBox.warning(self, "Dựng nháp", "Kịch bản còn thiếu, hãy sửa các mục báo đỏ:\n\n" + "\n".join(self._script.problems()))
            return
        clip_id, settings, db = self._clip_id, self.ctx.settings, self.ctx.db
        self.ctx.media.start(
            "draft", lambda report, cancel: runner.render_clip_job(settings, db, clip_id, False, report, cancel)
        )

    def _on_finished(self, kind: str, result, error) -> None:
        self._update_buttons()
        if kind not in ("rewrite", "draft") or not self.isVisible():
            return
        if isinstance(error, Cancelled):
            return
        if error is not None:
            QMessageBox.warning(self, "Kịch bản", str(error))
            self._show_clip(self._clip_id)
            return
        if kind == "rewrite":
            self._load_clips(keep=self._clip_id)
        else:
            if result.warnings:
                QMessageBox.information(self, "Dựng nháp", "Đã dựng nháp, có lưu ý:\n" + "\n".join(result.warnings))
            self.window().open_preview(clip_id=self._clip_id)
