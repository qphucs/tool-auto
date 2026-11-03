import logging
import shutil
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton
from sqlalchemy import select

from app.core.context import AppContext
from app.core.models import PROJECT_STATUS_LABELS, Project, ProjectStatus
from app.core.timeutil import fmt_local
from app.editor.ffmpeg import Cancelled
from app.pipeline import runner
from app.ui.pages.base import Page
from app.ui.widgets import fill_table, make_table, selected_ids

log = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
VIDEO_FILTER = "Video (" + " ".join(f"*{e}" for e in sorted(VIDEO_EXTS)) + ")"
LANGS = {"vi": "Tiếng Việt", "en": "Tiếng Anh"}


def _mmss(seconds: float | None) -> str:
    if not seconds:
        return ""
    m, s = divmod(int(seconds), 60)
    return f"{m // 60}:{m % 60:02d}:{s:02d}" if m >= 60 else f"{m}:{s:02d}"


class ProjectsPage(Page):
    title = "Dự án"
    subtitle = ("Thêm video gốc (bấm nút hoặc kéo thả file vào bảng), rồi bấm Phân tích. "
                "AI sẽ chép lời, tìm các kiến thức và viết kịch bản cho từng video ngắn.")
    HEADERS = ["Video gốc", "Thời lượng", "Ngôn ngữ", "Trạng thái", "Video ngắn", "Ngày thêm", "Ghi chú"]

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        bar = QHBoxLayout()
        self.add_btn = QPushButton("+ Thêm video gốc")
        self.add_btn.setObjectName("primary")
        self.analyze_btn = QPushButton("Phân tích")
        self.open_btn = QPushButton("Xem kịch bản")
        self.delete_btn = QPushButton("Xóa")
        for b in (self.add_btn, self.analyze_btn, self.open_btn, self.delete_btn):
            bar.addWidget(b)
        bar.addStretch(1)
        self.body.addLayout(bar)

        self.table = make_table(self.HEADERS)
        self.table.setAcceptDrops(True)
        self.table.viewport().setAcceptDrops(True)
        self.table.dragEnterEvent = self._drag_enter
        self.table.dragMoveEvent = self._drag_enter
        self.table.dropEvent = self._drop
        for col, width in enumerate((260, 80, 90, 130, 80, 120)):
            self.table.setColumnWidth(col, width)
        self.body.addWidget(self.table, 1)
        self.hint = QLabel()
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.body.addWidget(self.hint)

        self.add_btn.clicked.connect(self._pick)
        self.analyze_btn.clicked.connect(self._analyze)
        self.open_btn.clicked.connect(self._open_scripts)
        self.table.itemDoubleClicked.connect(lambda _: self._open_scripts())
        self.delete_btn.clicked.connect(self._delete)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        ctx.media.finished.connect(self._on_finished)
        ctx.media.started.connect(lambda _: self._update_buttons())
        self._update_buttons()

    def on_show(self) -> None:
        with self.ctx.db.session() as s:
            projects = s.scalars(select(Project).order_by(Project.created_at.desc())).all()
            rows = [
                (p.id, [
                    p.name, _mmss(p.duration), LANGS.get(p.language, p.language), PROJECT_STATUS_LABELS[p.status],
                    str(len(p.clips)) if p.clips else "", fmt_local(p.created_at), p.error.splitlines()[0] if p.error else "",
                ])
                for p in projects
            ]
        fill_table(self.table, rows)
        if not self.ctx.settings.ai.text.provider or self.ctx.settings.ai.text.provider == "none":
            self.hint.setText("⚠ Chưa chọn AI viết kịch bản. Vào trang Cài đặt để chọn hãng AI và nhập API key trước khi phân tích.")
        else:
            self.hint.setText("Lần phân tích đầu tiên sẽ tải model Whisper (khoảng 0.5GB). Video 30 phút có thể mất 10 phút trở lên để chép lời.")

    def _update_buttons(self) -> None:
        ids = selected_ids(self.table)
        busy = self.ctx.media.running
        self.analyze_btn.setEnabled(len(ids) == 1 and not busy)
        self.open_btn.setEnabled(len(ids) == 1)
        self.delete_btn.setEnabled(bool(ids) and not busy)

    # ----- thêm video -----

    def add_videos(self, paths: list[Path]) -> int:
        added = 0
        with self.ctx.db.session() as s:
            for p in paths:
                if p.suffix.lower() in VIDEO_EXTS and p.is_file():
                    duration, _ = runner.source_info(p)
                    s.add(Project(name=p.stem, source_path=str(p), duration=duration))
                    added += 1
            s.commit()
        self.on_show()
        return added

    def _pick(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Chọn video gốc", "", VIDEO_FILTER)
        self.add_videos([Path(p) for p in paths])

    def _drag_enter(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop(self, event) -> None:
        self.add_videos([Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()

    # ----- phân tích -----

    def _analyze(self) -> None:
        [project_id] = selected_ids(self.table)
        with self.ctx.db.session() as s:
            project = s.get(Project, project_id)
            has_clips = bool(project.clips)
        if has_clips:
            answer = QMessageBox.question(
                self, "Phân tích lại", "Video này đã có kịch bản. Phân tích lại sẽ thay toàn bộ kịch bản cũ.\n\nTiếp tục?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        settings, db = self.ctx.settings, self.ctx.db
        self.ctx.media.start("analyze", lambda report, cancel: runner.analyze_project(settings, db, project_id, report, cancel))
        self.on_show()
        self._update_buttons()

    def _on_finished(self, kind: str, result, error) -> None:
        self._update_buttons()
        if kind != "analyze":
            return
        self.on_show()
        if isinstance(error, Cancelled):
            return
        if error is not None:
            QMessageBox.warning(self, "Phân tích", f"Phân tích thất bại:\n{error}")
        else:
            QMessageBox.information(self, "Phân tích", f"Đã có {result} kịch bản. Mở trang Kịch bản để duyệt.")

    def _open_scripts(self) -> None:
        ids = selected_ids(self.table)
        if len(ids) == 1:
            self.window().open_scripts(project_id=ids[0])

    def _delete(self) -> None:
        ids = selected_ids(self.table)
        answer = QMessageBox.question(
            self, "Xóa dự án",
            f"Xóa {len(ids)} dự án khỏi tool?\n\nBản chép lời, kịch bản và bản nháp sẽ bị xóa. "
            "File video gốc và video thành phẩm trong thư mục outputs được giữ nguyên.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        with self.ctx.db.session() as s:
            for project_id in ids:
                project = s.get(Project, project_id)
                if project and project.status != ProjectStatus.ANALYZING:
                    s.delete(project)
                    shutil.rmtree(runner.project_dir(self.ctx.settings, project_id), ignore_errors=True)
            s.commit()
        self.on_show()
