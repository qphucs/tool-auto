from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.core.context import AppContext


class Page(QWidget):
    title = ""
    subtitle = ""

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.setSpacing(6)

        title = QLabel(self.title)
        title.setObjectName("pageTitle")
        outer.addWidget(title)
        if self.subtitle:
            subtitle = QLabel(self.subtitle)
            subtitle.setObjectName("pageSubtitle")
            subtitle.setWordWrap(True)
            outer.addWidget(subtitle)
        outer.addSpacing(14)

        self.body = QVBoxLayout()
        self.body.setSpacing(14)
        outer.addLayout(self.body, 1)

    def on_show(self) -> None:
        """Gọi mỗi khi người dùng chuyển sang trang này."""


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 16, 20, 16)
    return frame, layout


class PlaceholderPage(Page):
    """Trang chưa làm: hiện giai đoạn sẽ làm và danh sách tính năng dự kiến."""

    phase = ""
    planned: tuple[str, ...] = ()

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        frame, layout = card()
        badge = QLabel(f"Sẽ có ở {self.phase}")
        badge.setObjectName("phaseBadge")
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(6)
        for item in self.planned:
            label = QLabel(f"•  {item}")
            label.setWordWrap(True)
            layout.addWidget(label)
        self.body.addWidget(frame)
        self.body.addStretch(1)
