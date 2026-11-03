import json
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from app.core.context import AppContext
from app.core.media import probe
from app.core.models import StyleTemplate, Video
from app.editor.analyzer import analyze_sample
from app.editor.ffmpeg import Cancelled
from app.editor.planner import MODE_LABELS
from app.editor.renderer import RenderJob, RenderResult, render
from app.editor.template import FRAMING_LABELS, TemplateSpec
from app.ui.pages.base import Page

log = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
VIDEO_FILTER = "Video (" + " ".join(f"*{e}" for e in sorted(VIDEO_EXTS)) + ")"
SIZE_PRESETS = (
    ("sample", "Giống video mẫu"),
    ("1080x1920", "1080x1920 (dọc, TikTok/Shorts/Reels)"),
    ("1920x1080", "1920x1080 (ngang, YouTube)"),
    ("1080x1080", "1080x1080 (vuông)"),
)
TITLE_POSITIONS = (("top", "Trên"), ("center", "Giữa"), ("bottom", "Dưới"))
SUB_POSITIONS = (("bottom", "Dưới"), ("middle", "Giữa"), ("top", "Trên"))
SUB_SIZES = (("small", "Nhỏ"), ("medium", "Vừa"), ("large", "Lớn"))


def _combo(items) -> QComboBox:
    combo = QComboBox()
    for key, label in items:
        combo.addItem(label, key)
    return combo


def _select(combo: QComboBox, key) -> None:
    combo.setCurrentIndex(max(combo.findData(key), 0))


class VideoList(QListWidget):
    """Danh sách video gốc, nhận kéo thả file từ Explorer."""

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setMinimumHeight(80)
        self.setMaximumHeight(150)

    def add_paths(self, paths: list[Path]) -> int:
        existing = set(self.paths())
        added = 0
        for p in paths:
            if p.suffix.lower() in VIDEO_EXTS and p.is_file() and p not in existing:
                item = QListWidgetItem(f"{p.name}   ·   {probe(p).describe()}")
                item.setData(Qt.ItemDataRole.UserRole, str(p))
                item.setToolTip(str(p))
                self.addItem(item)
                existing.add(p)
                added += 1
        return added

    def paths(self) -> list[Path]:
        return [Path(self.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.count())]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self.add_paths([Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()


class EditorPage(Page):
    title = "Dựng video"
    subtitle = "Chọn video mẫu và video gốc. Tool đo nhịp cắt, khung hình, màu của mẫu rồi dựng video gốc theo đúng phong cách đó."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self.spec: TemplateSpec | None = None
        self.task = ctx.media

        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 8, 0)
        col.addWidget(self._sample_group())
        col.addWidget(self._sources_group())
        col.addWidget(self._options_group())
        col.addWidget(self._results_group())
        col.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        self.body.addWidget(scroll, 1)
        self.body.addLayout(self._run_bar())

        self.task.progress.connect(self._on_progress)
        self.task.finished.connect(self._on_finished)
        self._set_spec(None)
        self._update_busy()

    # ----- dựng giao diện -----

    def _sample_group(self) -> QGroupBox:
        box = QGroupBox("1. Video mẫu")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.pick_sample_btn = QPushButton("Chọn video mẫu...")
        self.pick_sample_btn.setObjectName("primary")
        self.saved = QComboBox()
        self.saved.setMinimumWidth(160)
        self.save_tpl_btn = QPushButton("Lưu thành mẫu phong cách...")
        row.addWidget(self.pick_sample_btn)
        row.addWidget(QLabel("hoặc dùng mẫu đã lưu:"))
        row.addWidget(self.saved, 1)
        row.addWidget(self.save_tpl_btn)
        layout.addLayout(row)
        self.sample_summary = QLabel()
        self.sample_summary.setWordWrap(True)
        self.sample_summary.setObjectName("muted")
        layout.addWidget(self.sample_summary)

        self.pick_sample_btn.clicked.connect(self._pick_sample)
        self.saved.activated.connect(self._use_saved)
        self.save_tpl_btn.clicked.connect(self._save_template)
        return box

    def _sources_group(self) -> QGroupBox:
        box = QGroupBox("2. Video gốc (kéo thả file vào đây)")
        layout = QVBoxLayout(box)
        self.sources = VideoList()
        layout.addWidget(self.sources)
        row = QHBoxLayout()
        add = QPushButton("Thêm video...")
        remove = QPushButton("Bỏ video đã chọn")
        clear = QPushButton("Bỏ hết")
        for b in (add, remove, clear):
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)
        add.clicked.connect(self._add_sources)
        remove.clicked.connect(lambda: [self.sources.takeItem(self.sources.row(i)) for i in self.sources.selectedItems()])
        clear.clicked.connect(self.sources.clear)
        return box

    def _options_group(self) -> QGroupBox:
        box = QGroupBox("3. Cách dựng")
        form = QFormLayout(box)

        self.mode = _combo(MODE_LABELS.items())
        self.clip_count = QSpinBox()
        self.clip_count.setRange(0, 10)
        self.clip_count.setSpecialValueText("Tự động")
        self.clip_count.setSuffix(" clip")
        self.mode.currentIndexChanged.connect(lambda: self.clip_count.setEnabled(self.mode.currentData() in ("split", "auto")))
        form.addRow("Cách dựng", self.mode)
        form.addRow("Số clip (khi cắt video dài)", self.clip_count)

        self.size = _combo(SIZE_PRESETS)
        self.framing = _combo(FRAMING_LABELS.items())
        form.addRow("Kích thước", self.size)
        form.addRow("Khung hình", self.framing)

        self.match_color = QCheckBox("Chỉnh màu giống mẫu")
        self.zoom = QCheckBox("Zoom nhẹ trong từng cảnh")
        self.fade = QCheckBox("Mờ dần khi chuyển cảnh")
        self.keep_audio = QCheckBox("Giữ âm thanh của video gốc")
        effects = QGridLayout()
        for i, cb in enumerate((self.match_color, self.zoom, self.fade, self.keep_audio)):
            effects.addWidget(cb, i // 2, i % 2)
        form.addRow("Hiệu ứng", effects)

        self.title_text = QLineEdit()
        self.title_text.setPlaceholderText("Để trống nếu không cần chữ trên video")
        form.addRow("Chữ tiêu đề", self.title_text)
        title_row = QHBoxLayout()
        self.title_pos = _combo(TITLE_POSITIONS)
        self.title_size = QSpinBox()
        self.title_size.setRange(24, 160)
        self.title_size.setSuffix(" px")
        self.title_secs = QSpinBox()
        self.title_secs.setRange(0, 600)
        self.title_secs.setSpecialValueText("suốt video")
        self.title_secs.setSuffix(" giây đầu")
        self.title_box = QCheckBox("Nền tối sau chữ")
        for label, w in (("Vị trí", self.title_pos), ("Cỡ", self.title_size)):
            title_row.addWidget(QLabel(label))
            title_row.addWidget(w)
        title_row.addWidget(self.title_box)
        title_row.addStretch(1)
        form.addRow("", title_row)
        form.addRow("Hiện chữ trong", self.title_secs)

        srt_row = QHBoxLayout()
        self.srt_path = QLineEdit()
        self.srt_path.setReadOnly(True)
        self.srt_path.setPlaceholderText("Không có phụ đề (chỉ dùng khi có đúng một video gốc)")
        pick_srt = QPushButton("Chọn .srt...")
        clear_srt = QPushButton("Bỏ")
        srt_row.addWidget(self.srt_path, 1)
        srt_row.addWidget(pick_srt)
        srt_row.addWidget(clear_srt)
        form.addRow("Phụ đề", srt_row)
        sub_row = QHBoxLayout()
        self.sub_pos = _combo(SUB_POSITIONS)
        self.sub_size = _combo(SUB_SIZES)
        sub_row.addWidget(QLabel("Vị trí"))
        sub_row.addWidget(self.sub_pos)
        sub_row.addWidget(QLabel("Cỡ"))
        sub_row.addWidget(self.sub_size)
        sub_row.addStretch(1)
        form.addRow("", sub_row)
        pick_srt.clicked.connect(self._pick_srt)
        clear_srt.clicked.connect(self.srt_path.clear)
        return box

    def _results_group(self) -> QGroupBox:
        box = QGroupBox("Kết quả")
        layout = QVBoxLayout(box)
        self.results = QListWidget()
        self.results.setMinimumHeight(90)
        layout.addWidget(self.results)
        row = QHBoxLayout()
        open_btn = QPushButton("Xem video")
        folder_btn = QPushButton("Mở thư mục kết quả")
        row.addWidget(open_btn)
        row.addWidget(folder_btn)
        row.addStretch(1)
        layout.addLayout(row)
        open_btn.clicked.connect(self._open_result)
        self.results.itemDoubleClicked.connect(lambda _: self._open_result())
        folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._out_dir()))))
        return box

    def _run_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.render_btn = QPushButton("Dựng video")
        self.render_btn.setObjectName("primary")
        self.cancel_btn = QPushButton("Hủy")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.status = QLabel()
        self.status.setObjectName("muted")
        row.addWidget(self.render_btn)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.progress, 1)
        row.addWidget(self.status, 2)
        self.render_btn.clicked.connect(self._render)
        self.cancel_btn.clicked.connect(lambda: self.task.cancel())
        return row

    # ----- mẫu -----

    def on_show(self) -> None:
        current = self.saved.currentData()
        self.saved.clear()
        self.saved.addItem("— Chọn —", None)
        with self.ctx.db.session() as s:
            for t in s.scalars(select(StyleTemplate).order_by(StyleTemplate.name)):
                self.saved.addItem(t.name, t.id)
        _select(self.saved, current)

    def _set_spec(self, spec: TemplateSpec | None) -> None:
        self.spec = spec
        self.save_tpl_btn.setEnabled(spec is not None)
        if spec is None:
            self.sample_summary.setText("Chưa có video mẫu.")
            return
        self.sample_summary.setText(spec.summary())
        _select(self.size, "sample")
        _select(self.framing, spec.framing)
        self.match_color.setChecked(spec.match_color)
        self.match_color.setEnabled(spec.brightness is not None)
        self.zoom.setChecked(spec.zoom)
        self.fade.setChecked(spec.fade)
        self.keep_audio.setChecked(spec.keep_audio)
        _select(self.title_pos, spec.text.position)
        self.title_size.setValue(spec.text.font_size)
        self.title_secs.setValue(int(spec.text.seconds))
        self.title_box.setChecked(spec.text.box)
        _select(self.sub_pos, spec.subtitle.position)
        _select(self.sub_size, spec.subtitle.size)

    def current_spec(self) -> TemplateSpec | None:
        """Mẫu đã phân tích cộng với các tùy chỉnh đang chọn trên giao diện."""
        if self.spec is None:
            return None
        spec = self.spec.copy()
        size = self.size.currentData()
        if size != "sample":
            spec.width, spec.height = map(int, size.split("x"))
        spec.framing = self.framing.currentData()
        spec.match_color = self.match_color.isChecked()
        spec.zoom = self.zoom.isChecked()
        spec.fade = self.fade.isChecked()
        spec.keep_audio = self.keep_audio.isChecked()
        spec.text.position = self.title_pos.currentData()
        spec.text.font_size = self.title_size.value()
        spec.text.seconds = self.title_secs.value()
        spec.text.box = self.title_box.isChecked()
        spec.subtitle.position = self.sub_pos.currentData()
        spec.subtitle.size = self.sub_size.currentData()
        return spec

    def _pick_sample(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn video mẫu", "", VIDEO_FILTER)
        if path:
            self.analyze(Path(path))

    def analyze(self, path: Path) -> None:
        self.status.setText(f"Đang phân tích video mẫu: {path.name}")
        self.task.start("analyze", lambda report, cancel: analyze_sample(path, cancel))
        self._update_busy()

    def _use_saved(self) -> None:
        template_id = self.saved.currentData()
        if template_id is None:
            return
        with self.ctx.db.session() as s:
            t = s.get(StyleTemplate, template_id)
            spec = TemplateSpec.from_dict(json.loads(t.spec_json))
        self._set_spec(spec)
        self.status.setText(f"Đang dùng mẫu: {self.saved.currentText()}")

    def _save_template(self) -> None:
        spec = self.current_spec()
        if spec is None:
            return
        default = Path(spec.sample_file).stem if spec.sample_file else "Mẫu mới"
        name, ok = QInputDialog.getText(self, "Lưu mẫu phong cách", "Tên mẫu:", text=default)
        if not ok or not name.strip():
            return
        with self.ctx.db.session() as s:
            t = StyleTemplate(name=name.strip(), source_video=spec.sample_file, spec_json=json.dumps(spec.to_dict(), ensure_ascii=False))
            s.add(t)
            s.commit()
            template_id = t.id
        self.on_show()
        _select(self.saved, template_id)
        self.status.setText(f"Đã lưu mẫu: {name.strip()}")

    # ----- video gốc, phụ đề -----

    def _add_sources(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Chọn video gốc", "", VIDEO_FILTER)
        self.sources.add_paths([Path(p) for p in paths])

    def _pick_srt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn phụ đề", "", "Phụ đề (*.srt)")
        if path:
            self.srt_path.setText(path)

    # ----- dựng -----

    def _out_dir(self) -> Path:
        return self.ctx.settings.data_path / "renders"

    def build_job(self) -> RenderJob | None:
        problems = []
        spec = self.current_spec()
        if spec is None:
            problems.append("Hãy chọn video mẫu hoặc một mẫu đã lưu.")
        sources = self.sources.paths()
        if not sources:
            problems.append("Hãy thêm ít nhất một video gốc.")
        missing = [p.name for p in sources if not p.is_file()]
        if missing:
            problems.append("Không tìm thấy: " + ", ".join(missing))
        if problems:
            QMessageBox.warning(self, "Dựng video", "\n".join(problems))
            return None
        return RenderJob(
            spec=spec,
            sources=sources,
            out_dir=self._out_dir(),
            mode=self.mode.currentData(),
            clip_count=self.clip_count.value(),
            title=self.title_text.text(),
            srt=Path(self.srt_path.text()) if self.srt_path.text() else None,
        )

    def _render(self) -> None:
        job = self.build_job()
        if job is None:
            return
        self.progress.setValue(0)
        self.task.start("render", lambda report, cancel: render(job, report, cancel))
        self._update_busy()

    def _update_busy(self) -> None:
        busy = self.task.running
        for w in (self.render_btn, self.pick_sample_btn, self.saved, self.save_tpl_btn):
            w.setEnabled(not busy and (w is not self.save_tpl_btn or self.spec is not None))
        self.cancel_btn.setEnabled(busy)
        if busy and self.status.text().startswith("Đang phân tích"):
            self.progress.setRange(0, 0)  # chưa biết tiến độ: thanh chạy liên tục
        else:
            self.progress.setRange(0, 1000)

    def _on_progress(self, fraction: float, message: str) -> None:
        self.progress.setRange(0, 1000)
        self.progress.setValue(int(fraction * 1000))
        self.status.setText(message)

    def _on_finished(self, kind: str, result, error) -> None:
        self._update_busy()
        if isinstance(error, Cancelled):
            self.status.setText("Đã hủy.")
            self.progress.setValue(0)
            return
        if error is not None:
            self.status.setText("Có lỗi, xem chi tiết trong hộp thoại.")
            QMessageBox.warning(self, "Dựng video", str(error))
            return
        if kind == "analyze":
            self._set_spec(result)
            _select(self.saved, None)
            self.status.setText("Đã phân tích xong video mẫu.")
        elif kind == "render":
            self._show_results(result)

    def _show_results(self, result: RenderResult) -> None:
        with self.ctx.db.session() as s:
            for out in result.outputs:
                info = probe(out)
                s.add(Video(file_path=str(out), title=out.stem, duration_sec=info.duration, width=info.width, height=info.height))
            s.commit()
        for out in reversed(result.outputs):
            item = QListWidgetItem(f"{out.name}   ·   {probe(out).describe()}")
            item.setData(Qt.ItemDataRole.UserRole, str(out))
            self.results.insertItem(0, item)
        self.results.setCurrentRow(0)
        self.status.setText(f"Xong: {len(result.outputs)} video ({MODE_LABELS[result.mode].lower()}).")
        if result.warnings:
            QMessageBox.information(self, "Dựng video", "\n".join(result.warnings))

    def _open_result(self) -> None:
        item = self.results.currentItem()
        if item:
            QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole)))
