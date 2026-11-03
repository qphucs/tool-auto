import json
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from app.core.context import AppContext
from app.core.models import CLIP_STATUS_LABELS, Clip, ClipStatus
from app.editor.ffmpeg import Cancelled, FFmpegError, run
from app.pipeline import runner
from app.render.scenes import SCENES
from app.ui.pages.base import Page

MUSIC_FILTER = "Nhạc (*.mp3 *.wav *.m4a *.aac *.ogg *.flac)"


def scene_thumbnails(video: Path, durations: list[float], out_dir: Path) -> list[Path]:
    """Một ảnh ở giữa mỗi cảnh. Dùng lại nếu video nháp chưa đổi."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(video.stat().st_mtime)
    thumbs, start = [], 0.0
    for i, d in enumerate(durations):
        thumb = out_dir / f"{stamp}-{i}.jpg"
        if not thumb.exists():
            t = start + min(max(d - 0.6, 0.0), 2.4)
            run(["-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=180:-2", str(thumb)])
        thumbs.append(thumb)
        start += d
    for old in out_dir.glob("*.jpg"):  # dọn ảnh của bản nháp cũ
        if not old.name.startswith(f"{stamp}-"):
            old.unlink(missing_ok=True)
    return thumbs


class PreviewPage(Page):
    title = "Xem nháp"
    subtitle = ("Xem bản nháp 540x960. Cảnh nào chưa ưng thì chọn cảnh đó rồi bấm Sửa cảnh. "
                "Dựng lại nháp chỉ dựng lại các cảnh đã đổi. Xong thì chọn nhạc và dựng bản cuối 1080x1920.")

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self._clip_id: int | None = None

        self.clips = QListWidget()
        self.clips.setMinimumWidth(220)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self.info = QLabel()
        self.info.setWordWrap(True)
        rl.addWidget(self.info)

        row = QHBoxLayout()
        self.play_btn = QPushButton("▶ Xem nháp")
        self.play_btn.setObjectName("primary")
        self.redraft_btn = QPushButton("Dựng lại nháp")
        self.edit_btn = QPushButton("Sửa cảnh đã chọn")
        for b in (self.play_btn, self.redraft_btn, self.edit_btn):
            row.addWidget(b)
        row.addStretch(1)
        rl.addLayout(row)

        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListView.ViewMode.IconMode)
        self.thumbs.setIconSize(QSize(135, 240))
        self.thumbs.setResizeMode(QListView.ResizeMode.Adjust)
        self.thumbs.setMovement(QListView.Movement.Static)
        self.thumbs.setSpacing(8)
        self.thumbs.setWordWrap(True)
        rl.addWidget(self.thumbs, 1)

        music = QHBoxLayout()
        music.addWidget(QLabel("Nhạc nền:"))
        self.music = QLabel("Không có")
        self.music.setObjectName("muted")
        pick_music = QPushButton("Chọn nhạc...")
        clear_music = QPushButton("Bỏ nhạc")
        music.addWidget(self.music, 1)
        music.addWidget(pick_music)
        music.addWidget(clear_music)
        rl.addLayout(music)

        final = QHBoxLayout()
        final.addStretch(1)
        self.final_btn = QPushButton("Dựng bản cuối 1080x1920")
        self.final_btn.setObjectName("primary")
        self.open_final_btn = QPushButton("Xem bản cuối")
        final.addWidget(self.open_final_btn)
        final.addWidget(self.final_btn)
        rl.addLayout(final)

        splitter = QSplitter()
        splitter.addWidget(self.clips)
        splitter.addWidget(right)
        splitter.setSizes([240, 740])
        self.body.addWidget(splitter, 1)

        self.clips.currentRowChanged.connect(self._on_clip)
        self.play_btn.clicked.connect(lambda: self._open(self._paths()[0]))
        self.open_final_btn.clicked.connect(lambda: self._open(self._paths()[1]))
        self.redraft_btn.clicked.connect(lambda: self._render(final=False))
        self.final_btn.clicked.connect(lambda: self._render(final=True))
        self.edit_btn.clicked.connect(self._edit_scene)
        self.thumbs.itemDoubleClicked.connect(lambda _: self._edit_scene())
        pick_music.clicked.connect(self._pick_music)
        clear_music.clicked.connect(lambda: self._set_music(""))
        ctx.media.finished.connect(self._on_finished)
        ctx.media.started.connect(lambda _: self._update_buttons())
        self._update_buttons()

    def on_show(self) -> None:
        self.open(clip_id=self._clip_id)

    def open(self, clip_id: int | None = None) -> None:
        self.clips.blockSignals(True)
        self.clips.clear()
        with self.ctx.db.session() as s:
            clips = s.scalars(
                select(Clip).where(Clip.status.in_([ClipStatus.DRAFT, ClipStatus.FINAL])).order_by(Clip.updated_at.desc())
            ).all()
            for c in clips:
                item = QListWidgetItem(f"{c.title}\n    {c.project.name} · {CLIP_STATUS_LABELS[c.status]}")
                item.setData(Qt.ItemDataRole.UserRole, c.id)
                self.clips.addItem(item)
        self.clips.blockSignals(False)
        ids = [self.clips.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.clips.count())]
        row = ids.index(clip_id) if clip_id in ids else (0 if ids else -1)
        self.clips.setCurrentRow(row)
        if row < 0:
            self._show(None)
        elif self.clips.currentRow() == row:
            self._show(ids[row])

    def _on_clip(self, row: int) -> None:
        item = self.clips.item(row) if row >= 0 else None
        self._show(item.data(Qt.ItemDataRole.UserRole) if item else None)

    def _paths(self) -> tuple[Path | None, Path | None]:
        if self._clip_id is None:
            return None, None
        with self.ctx.db.session() as s:
            clip = s.get(Clip, self._clip_id)
            draft = Path(clip.draft_path) if clip.draft_path and Path(clip.draft_path).is_file() else None
            final = Path(clip.final_path) if clip.final_path and Path(clip.final_path).is_file() else None
        return draft, final

    def _show(self, clip_id: int | None) -> None:
        self._clip_id = clip_id
        self.thumbs.clear()
        if clip_id is None:
            self.info.setText("Chưa có bản nháp nào. Duyệt một kịch bản ở trang Kịch bản để dựng nháp.")
            self.music.setText("Không có")
            self._update_buttons()
            return
        with self.ctx.db.session() as s:
            clip = s.get(Clip, clip_id)
            title, project_id, music, error = clip.title, clip.project_id, clip.music_path, clip.error
        draft, final = self._paths()
        self.music.setText(Path(music).name if music else "Không có")
        cdir = runner.clip_dir(self.ctx.settings, project_id, clip_id)
        timing_file = cdir / "draft.json"
        lines = [f"<b>{title}</b>"]
        if final:
            lines.append(f"Bản cuối: {final}")
        if error:
            lines.append(f"<span style='color:#b91c1c'>Lỗi lần dựng trước: {error}</span>")
        if draft and timing_file.exists():
            timing = json.loads(timing_file.read_text(encoding="utf-8"))
            total = sum(timing["durations"])
            lines.insert(1, f"Nháp dài {total:.0f} giây, {len(timing['durations'])} cảnh.")
            try:
                thumbs = scene_thumbnails(draft, timing["durations"], cdir / "thumbs")
            except FFmpegError:
                thumbs = []
            for i, (thumb, kind) in enumerate(zip(thumbs, timing["types"])):
                item = QListWidgetItem(QIcon(str(thumb)), f"{i + 1}. {SCENES[kind].label}")
                item.setData(Qt.ItemDataRole.UserRole, i)
                self.thumbs.addItem(item)
        self.info.setText("<br>".join(lines))
        self._update_buttons()

    def _update_buttons(self) -> None:
        busy = self.ctx.media.running
        draft, final = self._paths()
        self.play_btn.setEnabled(draft is not None)
        self.open_final_btn.setEnabled(final is not None)
        self.redraft_btn.setEnabled(self._clip_id is not None and not busy)
        self.final_btn.setEnabled(self._clip_id is not None and not busy)
        self.edit_btn.setEnabled(self._clip_id is not None)

    def _open(self, path: Path | None) -> None:
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _edit_scene(self) -> None:
        item = self.thumbs.currentItem()
        index = item.data(Qt.ItemDataRole.UserRole) if item else 0
        with self.ctx.db.session() as s:
            scene_count = len(json.loads(s.get(Clip, self._clip_id).script_json).get("scenes", []))
        if index >= scene_count:  # cảnh kêu gọi cuối video lấy từ trang Thương hiệu
            self.window().open_brand()
        else:
            self.window().open_scripts(clip_id=self._clip_id, scene_index=index)

    def _pick_music(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn nhạc nền", "", MUSIC_FILTER)
        if path:
            self._set_music(str(Path(path)))

    def _set_music(self, path: str) -> None:
        if self._clip_id is None:
            return
        with self.ctx.db.session() as s:
            s.get(Clip, self._clip_id).music_path = path
            s.commit()
        self.music.setText(Path(path).name if path else "Không có")

    def _render(self, final: bool) -> None:
        clip_id, settings, db = self._clip_id, self.ctx.settings, self.ctx.db
        self.ctx.media.start(
            "final" if final else "draft",
            lambda report, cancel: runner.render_clip_job(settings, db, clip_id, final, report, cancel),
        )

    def _on_finished(self, kind: str, result, error) -> None:
        self._update_buttons()
        if kind not in ("draft", "final") or not self.isVisible():
            return
        if isinstance(error, Cancelled):
            return
        if error is not None:
            QMessageBox.warning(self, "Dựng video", str(error))
        elif result.final:
            QMessageBox.information(self, "Dựng bản cuối", f"Đã dựng xong:\n{result.path}")
        self.open(clip_id=self._clip_id)
