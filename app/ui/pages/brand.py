import dataclasses
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.context import AppContext
from app.core.settings import BrandSettings, save_settings
from app.pipeline.assemble import cta_scene
from app.render.html_renderer import FrameJob, snapshot
from app.render.page import brand_payload, build_page
from app.render.sample import SAMPLE_SCENES
from app.render.scenes import clean_scene
from app.ui.pages.base import Page

COLORS = (
    ("bg1", "Nền (tối)"), ("bg2", "Nền (sáng)"), ("text", "Chữ"), ("muted", "Chữ phụ"),
    ("accent", "Màu nhấn 1 (chính)"), ("accent2", "Màu nhấn 2"), ("accent3", "Màu nhấn 3"), ("accent4", "Màu nhấn 4"),
)
PREVIEW_SCENES = ("hook", "steps")


def brand_preview(brand: BrandSettings, out_dir: Path) -> list[Path]:
    """Chụp vài cảnh mẫu với thương hiệu hiện tại (nhỏ, để xem nhanh)."""
    payload = brand_payload(brand)
    samples = {t: d for t, d, _ in SAMPLE_SCENES if t in PREVIEW_SCENES}
    scenes = [(t, samples[t]) for t in PREVIEW_SCENES]
    if brand.cta_enabled:
        cta = cta_scene(brand)
        scenes.append((cta.type, clean_scene(cta.type, cta.data)[0]))
    out = []
    for i, (scene_type, data) in enumerate(scenes):
        page = build_page(scene_type, data, 4.0, out_dir / f"brand-{i}.html", brand=payload, seed=7 + i)
        [shot] = snapshot(FrameJob(page, 4.0, 360, 640), [3.0], method="pw_png")
        path = out_dir / f"brand-{i}.png"
        path.write_bytes(shot)
        out.append(path)
    return out


class ColorButton(QPushButton):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(110)
        self.clicked.connect(self._pick)
        self.color = "#000000"

    def set_color(self, color: str) -> None:
        self.color = color
        text = "#111" if QColor(color).lightness() > 140 else "#fff"
        self.setText(color)
        self.setStyleSheet(f"background: {color}; color: {text}; border: 1px solid #d1d5db; border-radius: 6px; padding: 6px;")

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(self.color), self, "Chọn màu")
        if chosen.isValid():
            self.set_color(chosen.name())


class BrandPage(Page):
    title = "Thương hiệu"
    subtitle = "Màu sắc, font, logo, tên kênh và cảnh kêu gọi cuối video. Áp dụng cho mọi video dựng sau khi lưu."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 8, 0)

        colors = QGroupBox("Màu và font")
        grid = QGridLayout(colors)
        self.colors: dict[str, ColorButton] = {}
        for i, (key, label) in enumerate(COLORS):
            btn = ColorButton()
            grid.addWidget(QLabel(label), i // 2, (i % 2) * 2)
            grid.addWidget(btn, i // 2, (i % 2) * 2 + 1)
            self.colors[key] = btn
        self.font_box = QFontComboBox()
        grid.addWidget(QLabel("Font chữ"), 4, 0)
        grid.addWidget(self.font_box, 4, 1, 1, 3)
        col.addWidget(colors)

        channel = QGroupBox("Kênh")
        form = QFormLayout(channel)
        self.channel = QLineEdit()
        self.channel.setPlaceholderText("VD: AI Mỗi Ngày")
        logo_row = QHBoxLayout()
        self.logo = QLineEdit()
        self.logo.setReadOnly(True)
        pick = QPushButton("Chọn logo...")
        clear = QPushButton("Bỏ")
        logo_row.addWidget(self.logo, 1)
        logo_row.addWidget(pick)
        logo_row.addWidget(clear)
        self.show_logo = QCheckBox("Hiện logo và tên kênh ở góc video")
        form.addRow("Tên kênh", self.channel)
        form.addRow("Logo", logo_row)
        form.addRow(self.show_logo)
        pick.clicked.connect(self._pick_logo)
        clear.clicked.connect(self.logo.clear)
        col.addWidget(channel)

        cta = QGroupBox("Cảnh kêu gọi cuối video")
        form = QFormLayout(cta)
        self.cta_enabled = QCheckBox("Thêm cảnh kêu gọi vào cuối mỗi video")
        self.cta_question = QLineEdit()
        self.cta_hint = QLineEdit()
        self.cta_button = QLineEdit()
        form.addRow(self.cta_enabled)
        form.addRow("Câu hỏi", self.cta_question)
        form.addRow("Gợi ý", self.cta_hint)
        form.addRow("Chữ trên nút", self.cta_button)
        col.addWidget(cta)

        preview = QGroupBox("Xem trước")
        pv = QVBoxLayout(preview)
        self.preview_btn = QPushButton("Xem trước với cài đặt hiện tại")
        pv.addWidget(self.preview_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.previews = QHBoxLayout()
        pv.addLayout(self.previews)
        col.addWidget(preview)
        col.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        self.body.addWidget(scroll, 1)
        row = QHBoxLayout()
        reset = QPushButton("Về mặc định")
        save = QPushButton("Lưu thương hiệu")
        save.setObjectName("primary")
        row.addWidget(reset)
        row.addStretch(1)
        row.addWidget(save)
        self.body.addLayout(row)

        reset.clicked.connect(lambda: self._load(BrandSettings()))
        save.clicked.connect(self._save)
        self.preview_btn.clicked.connect(self._preview)
        ctx.media.finished.connect(self._on_finished)
        self._load(ctx.settings.brand)

    def _load(self, b: BrandSettings) -> None:
        for key, btn in self.colors.items():
            btn.set_color(getattr(b, key))
        self.font_box.setCurrentText(b.font)
        self.channel.setText(b.channel)
        self.logo.setText(b.logo)
        self.show_logo.setChecked(b.show_logo)
        self.cta_enabled.setChecked(b.cta_enabled)
        self.cta_question.setText(b.cta_question)
        self.cta_hint.setText(b.cta_hint)
        self.cta_button.setText(b.cta_button)

    def current(self) -> BrandSettings:
        values = {key: btn.color for key, btn in self.colors.items()}
        return dataclasses.replace(
            BrandSettings(), **values, font=self.font_box.currentText(), channel=self.channel.text().strip(),
            logo=self.logo.text().strip(), show_logo=self.show_logo.isChecked(), cta_enabled=self.cta_enabled.isChecked(),
            cta_question=self.cta_question.text().strip(), cta_hint=self.cta_hint.text().strip(),
            cta_button=self.cta_button.text().strip(),
        )

    def _pick_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn logo", "", "Ảnh (*.png *.jpg *.jpeg *.webp *.svg)")
        if path:
            self.logo.setText(str(Path(path)))
            self.show_logo.setChecked(True)

    def _save(self) -> None:
        self.ctx.settings.brand = self.current()
        save_settings(self.ctx.settings)
        QMessageBox.information(self, "Thương hiệu", "Đã lưu. Video dựng từ giờ sẽ dùng thương hiệu mới.")

    def _preview(self) -> None:
        if self.ctx.media.running:
            QMessageBox.information(self, "Xem trước", "Đang có việc khác chạy, hãy chờ xong.")
            return
        brand = self.current()
        out_dir = Path(tempfile.gettempdir()) / "toolauto-brand"
        out_dir.mkdir(exist_ok=True)
        self.preview_btn.setEnabled(False)
        self.ctx.media.start("brand_preview", lambda report, cancel: brand_preview(brand, out_dir))

    def _on_finished(self, kind: str, result, error) -> None:
        if kind != "brand_preview":
            return
        self.preview_btn.setEnabled(True)
        while self.previews.count():
            w = self.previews.takeAt(0).widget()
            if w:
                w.deleteLater()
        if error is not None:
            QMessageBox.warning(self, "Xem trước", str(error))
            return
        for path in result:
            label = QLabel()
            label.setPixmap(QPixmap(str(path)).scaledToWidth(220, Qt.TransformationMode.SmoothTransformation))
            self.previews.addWidget(label)
        self.previews.addStretch(1)
