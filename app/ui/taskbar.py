from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from app.ui.tasks import BackgroundTask

TASK_LABELS = {
    "analyze": "Phân tích video gốc",
    "rewrite": "Viết lại kịch bản",
    "draft": "Dựng nháp",
    "final": "Dựng bản cuối",
    "demo": "Dựng video thử",
    "models": "Lấy danh sách model",
    "voice_test": "Thử giọng đọc",
}


class TaskBar(QWidget):
    """Thanh tiến độ chung ở cuối cửa sổ cho việc đang chạy nền."""

    def __init__(self, task: BackgroundTask):
        super().__init__()
        self.setObjectName("taskbar")
        self.task = task
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        self.label = QLabel()
        self.label.setObjectName("muted")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(260)
        self.cancel_btn = QPushButton("Hủy")
        layout.addWidget(self.label, 1)
        layout.addWidget(self.bar)
        layout.addWidget(self.cancel_btn)
        self.cancel_btn.clicked.connect(self._cancel)
        task.started.connect(self._on_started)
        task.progress.connect(self._on_progress)
        task.finished.connect(lambda *a: self.hide())
        self.hide()

    def _on_started(self, kind: str) -> None:
        self.label.setText(f"{TASK_LABELS.get(kind, kind)}...")
        self.bar.setRange(0, 0)  # chưa có tiến độ: thanh chạy liên tục
        self.cancel_btn.setEnabled(True)
        self.show()

    def _on_progress(self, fraction: float, message: str) -> None:
        self.bar.setRange(0, 1000)
        self.bar.setValue(int(fraction * 1000))
        self.label.setText(message)

    def _cancel(self) -> None:
        self.task.cancel()
        self.cancel_btn.setEnabled(False)
        self.label.setText("Đang hủy...")
