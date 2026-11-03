"""Ô sửa một cảnh, tạo tự động theo khuôn dữ liệu của loại cảnh (app/render/scenes.py)."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.pipeline.script import VISUAL_KINDS, Scene, Visual
from app.render.scenes import SCENES, Choice, Focus, Image, Items, Number, Text

FIELD_LABELS = {
    "tag": "Nhãn chủ đề", "line1": "Tiêu đề dòng 1", "line2": "Tiêu đề dòng 2 (nhấn màu)", "accent": "Màu nhấn",
    "chips": "Các thẻ", "icon": "Biểu tượng (emoji)", "sub": "Chú thích", "value": "Con số",
    "decimals": "Số chữ số thập phân", "prefix": "Chữ trước số", "suffix": "Đơn vị sau số", "label": "Mô tả con số",
    "note": "Ghi chú", "url": "Địa chỉ trên thanh trình duyệt", "focus": "Phóng to vào", "caption": "Nhãn dưới ảnh",
    "caption_icon": "Biểu tượng nhãn", "items": "Các mục", "nodes": "Các bước của sơ đồ", "level": "Mức độ",
    "title": "Tiêu đề", "text": "Nội dung", "bullets": "Các ý", "question": "Câu hỏi", "hint": "Gợi ý",
    "button": "Chữ trên nút", "button_icon": "Biểu tượng nút",
}
CHOICE_LABELS = {
    "accent": "Màu nhấn 1", "accent-2": "Màu nhấn 2", "accent-3": "Màu nhấn 3", "accent-4": "Màu nhấn 4",
    "tip": "Mẹo", "warning": "Cảnh báo", "danger": "Nguy hiểm",
}
# Các trường giữ lại khi đổi loại cảnh
SHARED_FIELDS = ("tag", "line1", "line2", "accent")


def parse_mmss(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    try:
        total = 0.0
        for part in text.split(":"):
            total = total * 60 + float(part)
        return total
    except ValueError:
        return None


def fmt_mmss(t: float | None) -> str:
    if t is None:
        return ""
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:04.1f}"


def _items_to_text(spec: Items, value) -> str:
    lines = []
    for it in value or []:
        if spec.plain or isinstance(it, str):
            lines.append(str(it))
        else:
            lines.append(f"{it.get('icon', '')} | {it.get('text', '')}" if it.get("icon") else str(it.get("text", "")))
    return "\n".join(lines)


def _text_to_items(spec: Items, text: str) -> list:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if spec.plain:
            out.append(line)
        elif "|" in line:
            icon, _, body = line.partition("|")
            out.append({"icon": icon.strip(), "text": body.strip()})
        else:
            out.append({"icon": "", "text": line})
    return out


class SceneEditor(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._scene: Scene | None = None
        self._widgets: dict = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        top = QFormLayout()
        self.type_combo = QComboBox()
        for key, spec in SCENES.items():
            self.type_combo.addItem(f"{spec.label} – {spec.purpose}", key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        top.addRow("Loại cảnh", self.type_combo)
        self.narration = QPlainTextEdit()
        self.narration.setPlaceholderText("Lời AI đọc trong cảnh này")
        self.narration.setFixedHeight(80)
        self.narration.textChanged.connect(self.changed)
        top.addRow("Lời đọc", self.narration)
        outer.addLayout(top)

        self.fields_box = QGroupBox("Chữ trên màn hình")
        self.fields_form = QFormLayout(self.fields_box)
        outer.addWidget(self.fields_box)

        self.visual_box = QGroupBox("Hình minh họa")
        vf = QFormLayout(self.visual_box)
        self.visual_kind = QComboBox()
        for key, label in VISUAL_KINDS.items():
            self.visual_kind.addItem(label, key)
        self.visual_kind.currentIndexChanged.connect(self._update_visual_fields)
        self.visual_time = QLineEdit()
        self.visual_time.setPlaceholderText("mm:ss trong video gốc")
        self.visual_url = QLineEdit()
        self.visual_url.setPlaceholderText("https://...")
        path_row = QHBoxLayout()
        self.visual_path = QLineEdit()
        self.visual_path.setReadOnly(True)
        pick = QPushButton("Chọn ảnh...")
        pick.clicked.connect(self._pick_image)
        path_row.addWidget(self.visual_path, 1)
        path_row.addWidget(pick)
        vf.addRow("Nguồn", self.visual_kind)
        vf.addRow("Thời điểm", self.visual_time)
        vf.addRow("Trang web", self.visual_url)
        vf.addRow("Ảnh", path_row)
        note = QLabel("Đổi thời điểm hoặc trang web thì bấm Lưu, ảnh sẽ được lấy lại khi dựng nháp.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        vf.addRow(note)
        outer.addWidget(self.visual_box)
        outer.addStretch(1)
        for w in (self.visual_time, self.visual_url):
            w.textChanged.connect(self.changed)

    # ----- nạp / lấy cảnh -----

    def set_scene(self, scene: Scene | None) -> None:
        # Chặn tín hiệu "changed" trong lúc nạp: nếu không, trang Kịch bản sẽ đọc ô sửa khi mới nạp
        # được một nửa và ghi đè dữ liệu (ví dụ xóa mất ảnh minh họa).
        self.blockSignals(True)
        try:
            self._scene = scene
            self.setEnabled(scene is not None)
            if scene is None:
                self._clear_fields()
                return
            self.type_combo.blockSignals(True)
            self.type_combo.setCurrentIndex(max(self.type_combo.findData(scene.type), 0))
            self.type_combo.blockSignals(False)
            self.narration.setPlainText(scene.narration)
            self._build_fields(scene.type, scene.data)
            v = scene.visual
            self.visual_kind.setCurrentIndex(max(self.visual_kind.findData(v.kind), 0))
            self.visual_time.setText(fmt_mmss(v.time))
            self.visual_url.setText(v.url)
            self.visual_path.setText(v.path)
            self._update_visual_fields()
        finally:
            self.blockSignals(False)

    def scene(self) -> Scene | None:
        if self._scene is None:
            return None
        scene_type = self.type_combo.currentData()
        data = {}
        for name, (spec, w) in self._widgets.items():
            if isinstance(spec, Text):
                if w.text().strip():
                    data[name] = w.text().strip()
            elif isinstance(spec, Choice):
                data[name] = w.currentData()
            elif isinstance(spec, Number):
                if w.text().strip():
                    data[name] = w.text().strip()
            elif isinstance(spec, Items):
                items = _text_to_items(spec, w.toPlainText())
                if items:
                    data[name] = items
            elif isinstance(spec, Focus):
                x, y, scale = w
                if scale.value() > 1.01:
                    data[name] = {"x": x.value(), "y": y.value(), "scale": scale.value()}
        kind = self.visual_kind.currentData()
        old = self._scene.visual
        url, time = self.visual_url.text().strip(), parse_mmss(self.visual_time.text())
        path = self.visual_path.text().strip()
        # Đổi nguồn ảnh thì bỏ ảnh cũ để lần dựng sau lấy lại
        if kind != "file" and (kind != old.kind or url != old.url or time != old.time):
            path = ""
        return Scene(scene_type, self.narration.toPlainText().strip(), data, Visual(kind, time, url, path))

    # ----- dựng ô nhập -----

    def _clear_fields(self) -> None:
        while self.fields_form.rowCount():
            self.fields_form.removeRow(0)
        self._widgets = {}

    def _build_fields(self, scene_type: str, data: dict) -> None:
        self._clear_fields()
        spec = SCENES[scene_type]
        for name, f in spec.fields.items():
            value = data.get(name)
            label = FIELD_LABELS.get(name, name)
            if isinstance(f, Text):
                w = QLineEdit(str(value) if value is not None else "")
                w.setPlaceholderText(f"tối đa {f.max_len} ký tự" + (", bắt buộc" if f.required else ""))
                w.textChanged.connect(self.changed)
            elif isinstance(f, Choice):
                w = QComboBox()
                for v in f.values:
                    w.addItem(CHOICE_LABELS.get(v, v), v)
                w.setCurrentIndex(max(w.findData(value if value in f.values else f.default), 0))
                w.currentIndexChanged.connect(self.changed)
            elif isinstance(f, Number):
                w = QLineEdit("" if value is None else (str(int(value)) if float(value).is_integer() else str(value)))
                w.textChanged.connect(self.changed)
            elif isinstance(f, Items):
                w = QPlainTextEdit(_items_to_text(f, value))
                w.setFixedHeight(90)
                hint = "mỗi dòng một mục" if f.plain else "mỗi dòng một mục, dạng: emoji | chữ"
                w.setPlaceholderText(f"{hint} (tối đa {f.max_items} mục)")
                w.textChanged.connect(self.changed)
            elif isinstance(f, Focus):
                value = value or {}
                spins = []
                row = QHBoxLayout()
                for key, default, lo, hi, text in (("x", 0.5, 0, 1, "ngang"), ("y", 0.3, 0, 1, "dọc"), ("scale", 1.0, 1, 2.5, "mức")):
                    s = QDoubleSpinBox()
                    s.setRange(lo, hi)
                    s.setSingleStep(0.1)
                    s.setValue(float(value.get(key, default)))
                    s.valueChanged.connect(self.changed)
                    row.addWidget(QLabel(text))
                    row.addWidget(s)
                    spins.append(s)
                row.addStretch(1)
                self.fields_form.addRow(label, row)
                self._widgets[name] = (f, spins)
                continue
            elif isinstance(f, Image):
                continue  # ảnh chọn ở nhóm "Hình minh họa"
            else:
                continue
            self.fields_form.addRow(label, w)
            self._widgets[name] = (f, w)
        self.visual_box.setVisible(scene_type == "screenshot")

    def _on_type_changed(self) -> None:
        current = self.scene()
        if current is None:
            return
        keep = {k: v for k, v in current.data.items() if k in SHARED_FIELDS}
        self._build_fields(self.type_combo.currentData(), keep)
        self.changed.emit()

    def _update_visual_fields(self) -> None:
        kind = self.visual_kind.currentData()
        self.visual_time.setEnabled(kind == "source")
        self.visual_url.setEnabled(kind == "web")
        self.changed.emit()

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh minh họa", "", "Ảnh (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.visual_path.setText(str(Path(path)))
            self.visual_kind.setCurrentIndex(self.visual_kind.findData("file"))
            self.changed.emit()
