import logging
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
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
from app.ai.providers import create_provider
from app.core import secrets
from app.core.context import AppContext
from app.core.settings import ProviderChoice, VoiceSettings, save_settings
from app.pipeline import tts
from app.pipeline.runner import GOOGLE_TTS_KEY
from app.pipeline.transcribe import MODEL_SIZES
from app.render.bench import render_demo
from app.ui.pages.base import Page

log = logging.getLogger(__name__)

LOW_DISK_GB = 10
VOICE_SAMPLE = "Xin chào, đây là giọng đọc thử. Ba mẹo dùng AI giúp bạn học nhanh gấp ba lần."
# Ô API key: (tên trong Credential Manager, nhãn)
KEY_FIELDS = [(secrets.ai_key_name(p.key), p.label) for p in PROVIDERS.values() if p.needs_api_key]
KEY_FIELDS.append((GOOGLE_TTS_KEY, "Google Cloud TTS (giọng đọc)"))


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


class ProviderPicker(QWidget):
    """Chọn hãng AI + model cho một việc."""

    def __init__(self, allow_none: bool, vision_only: bool = False):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.provider = QComboBox()
        for info in PROVIDERS.values():
            if info.key == "none":
                if allow_none:  # "Không dùng" luôn có khi được phép, kể cả với bộ lọc chỉ hãng đọc ảnh
                    self.provider.addItem(info.label, info.key)
            elif info.vision or not vision_only:
                self.provider.addItem(info.label, info.key)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumWidth(240)
        self.list_btn = QPushButton("Lấy danh sách model")
        layout.addWidget(self.provider)
        layout.addWidget(self.model, 1)
        layout.addWidget(self.list_btn)
        self.note = QLabel()
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        self.provider.currentIndexChanged.connect(self._on_provider)

    def set(self, choice: ProviderChoice) -> None:
        self.provider.setCurrentIndex(max(self.provider.findData(choice.provider), 0))
        self._on_provider()
        self.model.setEditText(choice.model)

    def get(self) -> ProviderChoice:
        return ProviderChoice(self.provider.currentData(), self.model.currentText().strip())

    def set_models(self, models: list[str]) -> None:
        current = self.model.currentText()
        self.model.clear()
        self.model.addItems(models)
        self.model.setEditText(current if current in models or not models else models[0])

    def _on_provider(self) -> None:
        info = PROVIDERS[self.provider.currentData()]
        self.model.clear()
        self.model.setEnabled(info.key != "none")
        self.list_btn.setEnabled(info.key != "none")
        self.model.lineEdit().setPlaceholderText(info.model_hint)
        if info.key == "claude":
            self.model.setEditText("claude-opus-5-5")
        self.note.setText(info.note)


class SettingsPage(Page):
    title = "Cài đặt"
    subtitle = "Các thay đổi chỉ có hiệu lực sau khi bấm Lưu cài đặt."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 8, 0)
        for group in (self._storage_group(), self._keys_group(), self._ai_group(), self._whisper_group(),
                      self._voice_group(), self._check_group()):
            col.addWidget(group)
        col.addStretch(1)
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

        ctx.media.finished.connect(self._on_task_finished)
        self._load()

    # ----- các nhóm -----

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

    def _keys_group(self) -> QGroupBox:
        box = QGroupBox("API key")
        form = QFormLayout(box)
        self.keys: dict[str, QLineEdit] = {}
        for name, label in KEY_FIELDS:
            w = QLineEdit()
            w.setEchoMode(QLineEdit.EchoMode.Password)
            w.setPlaceholderText("Chưa có")
            form.addRow(label, w)
            self.keys[name] = w
        note = QLabel("Key được cất trong Windows Credential Manager, không lưu trong file. Chỉ cần key của hãng bạn dùng.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)
        return box

    def _ai_group(self) -> QGroupBox:
        box = QGroupBox("AI")
        form = QFormLayout(box)
        self.text_ai = ProviderPicker(allow_none=False)
        self.vision_ai = ProviderPicker(allow_none=True, vision_only=True)
        form.addRow("Viết kịch bản", self.text_ai)
        form.addRow("", self.text_ai.note)
        form.addRow("Chọn khung hình", self.vision_ai)
        hint = QLabel("Model đọc được ảnh, dùng để chọn khung hình đẹp nhất từ video gốc. Chọn \"Không dùng\" thì tool lấy khung ở thời điểm AI gợi ý.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        form.addRow("", hint)
        self.ollama_url = QLineEdit()
        form.addRow("Địa chỉ Ollama", self.ollama_url)
        self.text_ai.list_btn.clicked.connect(lambda: self._list_models(self.text_ai))
        self.vision_ai.list_btn.clicked.connect(lambda: self._list_models(self.vision_ai))
        return box

    def _whisper_group(self) -> QGroupBox:
        box = QGroupBox("Chép lời (Whisper)")
        form = QFormLayout(box)
        self.whisper_model = QComboBox()
        for key, label in MODEL_SIZES.items():
            self.whisper_model.addItem(f"{key} – {label}", key)
        self.whisper_device = QComboBox()
        self.whisper_device.addItem("CPU (chạy ở mọi máy)", "cpu")
        self.whisper_device.addItem("GPU NVIDIA (nhanh hơn, cần cài CUDA và cuDNN)", "cuda")
        form.addRow("Model", self.whisper_model)
        form.addRow("Chạy bằng", self.whisper_device)
        return box

    def _voice_group(self) -> QGroupBox:
        box = QGroupBox("Giọng đọc")
        form = QFormLayout(box)
        self.voice_provider = QComboBox()
        for key, label in tts.PROVIDERS.items():
            self.voice_provider.addItem(label, key)
        self.voice_name = QComboBox()
        self.voice_name.setEditable(True)
        self.voice_name.setMinimumWidth(260)
        self.voice_rate = QSpinBox()
        self.voice_rate.setRange(-50, 50)
        self.voice_rate.setSuffix(" %")
        self.voice_rate.setToolTip("Nhanh hơn (+) hoặc chậm hơn (-) so với bình thường")
        test = QPushButton("Thử giọng")
        row = QHBoxLayout()
        row.addWidget(self.voice_name, 1)
        row.addWidget(test)
        form.addRow("Dịch vụ", self.voice_provider)
        form.addRow("Giọng", row)
        form.addRow("Tốc độ", self.voice_rate)
        self.voice_provider.currentIndexChanged.connect(self._fill_voices)
        test.clicked.connect(self._test_voice)
        return box

    def _check_group(self) -> QGroupBox:
        box = QGroupBox("Kiểm tra máy")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.demo_btn = QPushButton("Dựng video thử 10 giây")
        self.demo_open = QPushButton("Xem video thử")
        self.demo_open.setEnabled(False)
        row.addWidget(self.demo_btn)
        row.addWidget(self.demo_open)
        row.addStretch(1)
        layout.addLayout(row)
        self.demo_status = QLabel("Dựng một cảnh mẫu 1080x1920 để xem chất lượng và đo tốc độ dựng trên máy này.")
        self.demo_status.setObjectName("muted")
        self.demo_status.setWordWrap(True)
        layout.addWidget(self.demo_status)
        self._demo_video: Path | None = None
        self.demo_btn.clicked.connect(self._run_demo)
        self.demo_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._demo_video))))
        return box

    # ----- nạp / lưu -----

    def _load(self) -> None:
        s = self.ctx.settings
        self.data_dir.setText(s.data_dir)
        for name, w in self.keys.items():
            w.setText(secrets.get_secret(name))
        self.text_ai.set(s.ai.text)
        self.vision_ai.set(s.ai.vision)
        self.ollama_url.setText(s.ai.ollama_url)
        self.whisper_model.setCurrentIndex(max(self.whisper_model.findData(s.whisper.model), 0))
        self.whisper_device.setCurrentIndex(max(self.whisper_device.findData(s.whisper.device), 0))
        self.voice_provider.setCurrentIndex(max(self.voice_provider.findData(s.voice.provider), 0))
        self._fill_voices()
        index = self.voice_name.findData(s.voice.voice)
        if index >= 0:
            self.voice_name.setCurrentIndex(index)
        else:
            self.voice_name.setEditText(s.voice.voice)
        self.voice_rate.setValue(s.voice.rate)
        self._update_free_space()

    def _fill_voices(self) -> None:
        provider = self.voice_provider.currentData()
        voices = tts.windows_voices() if provider == "windows" else tts.VOICES.get(provider, [])
        self.voice_name.clear()
        for key, label in voices:
            self.voice_name.addItem(label, key)
        if provider == "windows" and not voices:
            self.voice_name.setEditText("")
            self.voice_name.lineEdit().setPlaceholderText("Không thấy giọng Windows nào")

    def _voice_name_value(self) -> str:
        """Ô giọng hiện nhãn ("Hoài My (nữ)"), lưu tên giọng thật ("vi-VN-HoaiMyNeural")."""
        text = self.voice_name.currentText().strip()
        index = self.voice_name.findText(text)
        return self.voice_name.itemData(index) if index >= 0 else text

    def _update_free_space(self) -> None:
        text = self.data_dir.text().strip()
        self.free_space.setText(free_space_text(Path(text)) if text else "")

    def _browse_data_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Chọn thư mục dữ liệu", self.data_dir.text())
        if chosen:
            self.data_dir.setText(str(Path(chosen)))

    def _save_keys(self) -> bool:
        try:
            for name, w in self.keys.items():
                value = w.text().strip()
                if value != secrets.get_secret(name):
                    secrets.set_secret(name, value)
        except Exception as e:  # keyring có thể báo nhiều loại lỗi khác nhau
            log.exception("Không lưu được API key")
            QMessageBox.warning(self, "Cài đặt", f"Không lưu được API key:\n{e}")
            return False
        return True

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
        if not self._save_keys():
            return
        dir_changed = Path(new_dir) != s.data_path
        s.data_dir = new_dir
        s.ai.text = self.text_ai.get()
        s.ai.vision = self.vision_ai.get()
        s.ai.ollama_url = self.ollama_url.text().strip() or "http://localhost:11434"
        s.whisper.model = self.whisper_model.currentData()
        s.whisper.device = self.whisper_device.currentData()
        s.voice = VoiceSettings(self.voice_provider.currentData(), self._voice_name_value(), self.voice_rate.value())
        save_settings(s)
        log.info("Đã lưu cài đặt")
        msg = "Đã lưu cài đặt."
        if dir_changed:
            msg += "\n\nThư mục dữ liệu mới sẽ được dùng sau khi khởi động lại app.\nDữ liệu cũ không tự chuyển sang."
        QMessageBox.information(self, "Cài đặt", msg)

    # ----- việc nền: danh sách model, thử giọng, video thử -----

    def _busy(self) -> bool:
        if self.ctx.media.running:
            QMessageBox.information(self, "Cài đặt", "Đang có việc khác chạy, hãy chờ xong.")
            return True
        return False

    def _list_models(self, picker: ProviderPicker) -> None:
        if self._busy() or not self._save_keys():
            return
        choice, ai = picker.get(), self.ctx.settings.ai
        ai.ollama_url = self.ollama_url.text().strip() or ai.ollama_url
        key = secrets.get_secret(secrets.ai_key_name(choice.provider))
        choice = ProviderChoice(choice.provider, choice.model or "x")  # một số hãng đòi có tên model
        self._models_target = picker
        self.ctx.media.start("models", lambda report, cancel: create_provider(choice, ai, key).list_models())

    def _test_voice(self) -> None:
        if self._busy() or not self._save_keys():
            return
        voice = VoiceSettings(self.voice_provider.currentData(), self._voice_name_value(), self.voice_rate.value())
        key = secrets.get_secret(GOOGLE_TTS_KEY)
        out_dir = Path(tempfile.gettempdir()) / "toolauto-voice-test"
        self.ctx.media.start("voice_test", lambda report, cancel: tts.synthesize(VOICE_SAMPLE, out_dir, voice, key, cancel))

    def _run_demo(self) -> None:
        if self._busy():
            return
        out_dir = self.ctx.settings.outputs_dir
        self.demo_btn.setEnabled(False)
        self.demo_status.setText("Đang dựng...")
        self.ctx.media.start("demo", lambda report, cancel: render_demo(out_dir, report, cancel))

    def _on_task_finished(self, kind: str, result, error) -> None:
        if kind == "models":
            if error is not None:
                QMessageBox.warning(self, "Danh sách model", str(error))
            else:
                self._models_target.set_models(result)
                self.window().statusBar().showMessage(f"Có {len(result)} model.", 5000)
        elif kind == "voice_test":
            if error is not None:
                QMessageBox.warning(self, "Thử giọng", str(error))
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(result.audio)))
        elif kind == "demo":
            self.demo_btn.setEnabled(True)
            if error is not None:
                self.demo_status.setText(f"Lỗi: {error}")
                return
            self._demo_video, stats = result
            self.demo_open.setEnabled(True)
            self.demo_status.setText(
                f"Xong trong {stats.seconds:.1f} giây ({stats.render_fps:.1f} khung hình/giây, "
                f"{stats.realtime_factor:.2f} giây dựng cho mỗi giây video). Ước tính một video 60 giây mất khoảng "
                f"{stats.realtime_factor:.1f} phút."  # x giây dựng/giây video × 60 giây = x phút
            )
