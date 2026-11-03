from PySide6.QtWidgets import QGridLayout, QLabel

from app.core.context import AppContext
from app.core.stats import dashboard_stats
from app.ui.pages.base import Page, card

STAT_CARDS = (
    ("accounts", "Tài khoản"),
    ("pending_review", "Chờ duyệt"),
    ("scheduled", "Đã lên lịch"),
    ("posted_today", "Đã đăng hôm nay"),
    ("problems", "Lỗi / cần xử lý"),
)


class DashboardPage(Page):
    title = "Tổng quan"
    subtitle = "Tình hình đăng bài trên mọi tài khoản."

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        grid = QGridLayout()
        grid.setSpacing(14)
        self._values: dict[str, QLabel] = {}
        for i, (key, label) in enumerate(STAT_CARDS):
            frame, layout = card()
            value = QLabel("0")
            value.setObjectName("statValue")
            caption = QLabel(label)
            caption.setObjectName("statLabel")
            layout.addWidget(value)
            layout.addWidget(caption)
            grid.addWidget(frame, i // 3, i % 3)
            self._values[key] = value
        self.body.addLayout(grid)

        frame, layout = card()
        self._storage = QLabel()
        self._storage.setObjectName("muted")
        self._storage.setWordWrap(True)
        layout.addWidget(self._storage)
        self.body.addWidget(frame)
        self.body.addStretch(1)
        self.on_show()

    def on_show(self) -> None:
        with self.ctx.db.session() as session:
            stats = dashboard_stats(session)
        for key, label in self._values.items():
            label.setText(str(getattr(stats, key)))
        self._storage.setText(f"Dữ liệu lưu tại: {self.ctx.settings.data_dir}")
