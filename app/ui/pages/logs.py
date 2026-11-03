from collections import deque

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton

from app.core.context import AppContext
from app.core.logging_setup import LOG_FILE
from app.ui.pages.base import Page

MAX_LINES = 500


class LogsPage(Page):
    title = "Nhật ký"
    subtitle = f"{MAX_LINES} dòng mới nhất của nhật ký hoạt động."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        buttons = QHBoxLayout()
        refresh = QPushButton("Làm mới")
        refresh.clicked.connect(self.on_show)
        open_dir = QPushButton("Mở thư mục nhật ký")
        open_dir.clicked.connect(self._open_dir)
        buttons.addWidget(refresh)
        buttons.addWidget(open_dir)
        buttons.addStretch(1)
        self.body.addLayout(buttons)

        self._text = QPlainTextEdit()
        self._text.setObjectName("logView")
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.body.addWidget(self._text, 1)

    def on_show(self) -> None:
        path = self.ctx.settings.logs_dir / LOG_FILE
        try:
            with path.open(encoding="utf-8", errors="replace") as f:
                lines = deque(f, maxlen=MAX_LINES)
            self._text.setPlainText("".join(lines))
        except FileNotFoundError:
            self._text.setPlainText("Chưa có nhật ký.")
        bar = self._text.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _open_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.settings.logs_dir)))
