import logging
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ai.base import PROVIDERS
from app.core import secrets
from app.core.context import AppContext
from app.core.settings import save_settings
from app.ui.pages.base import Page

log = logging.getLogger(__name__)

LOW_DISK_GB = 10


def free_space_text(path: Path) -> str:
    # Thư mục có thể chưa tồn tại: đo dung lượng trống của thư mục cha gần nhất
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        free_gb = shutil.disk_usage(probe).free / 1024**3
    except OSError:
        return "Không đo được dung lượng trống."
    warn = "  ⚠ Sắp đầy, nên chọn ổ khác." if free_gb < LOW_DISK_GB else ""
    return f"Ổ đĩa còn trống {free_gb:.1f} GB.{warn}"


class SettingsPage(Page):
    title = "Cài đặt"
    subtitle = "Các thay đổi chỉ có hiệu lực sau khi bấm Lưu."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        content = QWidget()
        form_area = QVBoxLayout(content)
        form_area.setContentsMargins(0, 0, 8, 0)
        form_area.addWidget(self._storage_group())
        form_area.addWidget(self._posting_group())
        form_area.addWidget(self._system_group())
        form_area.addWidget(self._ai_group())
        form_area.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        self.body.addWidget(scroll, 1)

        save = QPushButton("Lưu cài đặt")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(save)
        self.body.addLayout(row)

        self._load()

    # ----- các nhóm cài đặt -----

    def _storage_group(self) -> QGroupBox:
        box = QGroupBox("Lưu trữ")
        form = QFormLayout(box)
        self.data_dir = QLineEdit()
        self.data_dir.textChanged.connect(self._update_free_space)
        browse = QPushButton("Chọn...")
        browse.clicked.connect(self._browse_data_dir)
        row = QHBoxLayout()
        row.addWidget(self.data_dir, 1)
        row.addWidget(browse)
        form.addRow("Thư mục dữ liệu", row)
        self.free_space = QLabel()
        self.free_space.setObjectName("muted")
        form.addRow("", self.free_space)
        return box

    def _posting_group(self) -> QGroupBox:
        box = QGroupBox("Đăng bài")
        form = QFormLayout(box)
        self.min_gap = QSpinBox()
        self.min_gap.setRange(0, 1440)
        self.min_gap.setSuffix(" phút")
        form.addRow("Nghỉ tối thiểu giữa hai lần đăng", self.min_gap)
        self.max_retries = QSpinBox()
        self.max_retries.setRange(0, 10)
        self.max_retries.setSuffix(" lần")
        form.addRow("Số lần thử lại khi lỗi", self.max_retries)
        self.show_browser = QCheckBox("Hiện cửa sổ trình duyệt khi đăng (nên bật lúc mới dùng để theo dõi)")
        form.addRow(self.show_browser)
        return box

    def _system_group(self) -> QGroupBox:
        box = QGroupBox("Hệ thống")
        form = QFormLayout(box)
        self.start_with_windows = QCheckBox("Khởi động cùng Windows (GĐ4)")
        self.minimize_to_tray = QCheckBox("Thu nhỏ xuống khay hệ thống khi đóng (GĐ4)")
        for cb in (self.start_with_windows, self.minimize_to_tray):
            cb.setEnabled(False)
            form.addRow(cb)
        return box

    def _ai_group(self) -> QGroupBox:
        box = QGroupBox("AI (dùng từ GĐ5)")
        form = QFormLayout(box)
        self.ai_provider = QComboBox()
        for info in PROVIDERS.values():
            self.ai_provider.addItem(info.label, info.key)
        self.ai_provider.currentIndexChanged.connect(self._update_ai_fields)
        form.addRow("Nhà cung cấp", self.ai_provider)
        self.ai_endpoint = QLineEdit()
        form.addRow("Địa chỉ Ollama", self.ai_endpoint)
        self.ai_model = QLineEdit()
        form.addRow("Model", self.ai_model)
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API key", self.ai_key)
        self.ai_note = QLabel()
        self.ai_note.setObjectName("muted")
        self.ai_note.setWordWrap(True)
        form.addRow("", self.ai_note)
        return box

    # ----- nạp, cập nhật, lưu -----

    def _load(self) -> None:
        s = self.ctx.settings
        self.data_dir.setText(s.data_dir)
        self.min_gap.setValue(s.min_gap_minutes)
        self.max_retries.setValue(s.max_retries)
        self.show_browser.setChecked(s.show_browser)
        self.start_with_windows.setChecked(s.start_with_windows)
        self.minimize_to_tray.setChecked(s.minimize_to_tray)
        self.ai_endpoint.setText(s.ai.endpoint)
        self.ai_model.setText(s.ai.model)
        index = self.ai_provider.findData(s.ai.provider)
        self.ai_provider.setCurrentIndex(max(index, 0))
        self._update_ai_fields()
        self._update_free_space()

    def _current_provider(self) -> str:
        return self.ai_provider.currentData()

    def _update_ai_fields(self) -> None:
        info = PROVIDERS[self._current_provider()]
        self.ai_endpoint.setEnabled(info.needs_endpoint)
        self.ai_model.setEnabled(info.key != "none")
        self.ai_model.setPlaceholderText(info.model_hint)
        self.ai_key.setEnabled(info.needs_api_key)
        self.ai_key.setText(secrets.get_secret(secrets.ai_key_name(info.key)) if info.needs_api_key else "")
        self.ai_note.setText(info.note)

    def _update_free_space(self) -> None:
        text = self.data_dir.text().strip()
        self.free_space.setText(free_space_text(Path(text)) if text else "")

    def _browse_data_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Chọn thư mục dữ liệu", self.data_dir.text())
        if chosen:
            self.data_dir.setText(str(Path(chosen)))

    def _save(self) -> None:
        s = self.ctx.settings
        new_dir = self.data_dir.text().strip()
        if not new_dir:
            QMessageBox.warning(self, "Cài đặt", "Thư mục dữ liệu không được để trống.")
            return
        try:
            Path(new_dir).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "Cài đặt", f"Không tạo được thư mục dữ liệu:\n{e}")
            return

        provider = self._current_provider()
        if PROVIDERS[provider].needs_api_key:
            try:
                secrets.set_secret(secrets.ai_key_name(provider), self.ai_key.text().strip())
            except Exception as e:  # keyring có thể báo nhiều loại lỗi khác nhau
                log.exception("Không lưu được API key")
                QMessageBox.warning(self, "Cài đặt", f"Không lưu được API key:\n{e}")
                return

        dir_changed = Path(new_dir) != s.data_path
        s.data_dir = new_dir
        s.min_gap_minutes = self.min_gap.value()
        s.max_retries = self.max_retries.value()
        s.show_browser = self.show_browser.isChecked()
        s.ai.provider = provider
        s.ai.endpoint = self.ai_endpoint.text().strip()
        s.ai.model = self.ai_model.text().strip()
        save_settings(s)
        log.info("Đã lưu cài đặt")

        msg = "Đã lưu cài đặt."
        if dir_changed:
            msg += "\n\nThư mục dữ liệu mới sẽ được dùng sau khi khởi động lại app.\nDữ liệu cũ không tự chuyển sang."
        QMessageBox.information(self, "Cài đặt", msg)
