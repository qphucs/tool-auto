from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton
from sqlalchemy import select

from app.core import posting
from app.core.context import AppContext
from app.core.models import PLATFORM_LABELS, TARGET_STATUS_LABELS, PostTarget, TargetStatus, utcnow
from app.core.timeutil import fmt_local, local_to_utc, utc_to_local
from app.ui.pages.base import Page
from app.ui.widgets import ask_datetime, default_post_time, fill_table, make_table, selected_ids

S = TargetStatus
FILTERS = (
    ("Sắp đăng", (S.SCHEDULED, S.POSTING)),
    ("Lỗi / cần xử lý", (S.FAILED, S.NEEDS_ATTENTION)),
    ("Đã đăng", (S.SUCCESS,)),
    ("Tất cả", (S.SCHEDULED, S.POSTING, S.FAILED, S.NEEDS_ATTENTION, S.SUCCESS)),
)


class SchedulePage(Page):
    title = "Lịch đăng"
    subtitle = "Các video đã duyệt. Tool đăng lần lượt từng video khi đến giờ, khi máy đang bật."
    HEADERS = ["Giờ đăng", "Tài khoản", "Tiêu đề", "Trạng thái", "Lần thử", "Kết quả / lỗi"]

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        bar = QHBoxLayout()
        self.filter = QComboBox()
        for label, _ in FILTERS:
            self.filter.addItem(label)
        self.now_btn = QPushButton("Đăng ngay")
        self.reschedule_btn = QPushButton("Đổi giờ")
        self.unschedule_btn = QPushButton("Hủy lịch")
        self.retry_btn = QPushButton("Thử lại")
        self.open_btn = QPushButton("Mở link")
        self.shots_btn = QPushButton("Ảnh chụp lỗi")
        for w in (self.filter, self.now_btn, self.reschedule_btn, self.unschedule_btn, self.retry_btn, self.open_btn, self.shots_btn):
            bar.addWidget(w)
        bar.addStretch(1)
        self.body.addLayout(bar)

        self.state = QLabel()
        self.state.setObjectName("muted")
        self.body.addWidget(self.state)

        self.table = make_table(self.HEADERS)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 60)
        self.body.addWidget(self.table, 1)

        self.filter.currentIndexChanged.connect(self.on_show)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.now_btn.clicked.connect(self._post_now)
        self.reschedule_btn.clicked.connect(self._reschedule)
        self.unschedule_btn.clicked.connect(self._unschedule)
        self.retry_btn.clicked.connect(self._retry)
        self.open_btn.clicked.connect(self._open_links)
        self.shots_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.settings.data_path / "screenshots")))
        )
        self._statuses: dict[int, TargetStatus] = {}
        self._links: dict[int, str] = {}
        self._update_buttons()

    def on_show(self) -> None:
        statuses = FILTERS[self.filter.currentIndex()][1]
        done_only = statuses == (S.SUCCESS,)
        order = (PostTarget.posted_at.desc(),) if done_only else (PostTarget.scheduled_at, PostTarget.id)
        with self.ctx.db.session() as s:
            targets = s.scalars(select(PostTarget).where(PostTarget.status.in_(statuses)).order_by(*order)).all()
            rows = []
            self._statuses = {t.id: t.status for t in targets}
            self._links = {t.id: t.result_url for t in targets if t.result_url}
            for t in targets:
                when = t.posted_at if t.status == S.SUCCESS else t.scheduled_at
                rows.append(
                    (
                        t.id,
                        [
                            fmt_local(when),
                            f"{PLATFORM_LABELS[t.account.platform]} · {t.account.name}",
                            t.title,
                            TARGET_STATUS_LABELS[t.status],
                            str(t.attempts),
                            t.result_url or t.last_error,
                        ],
                    )
                )
        fill_table(self.table, rows)
        self.state.setText(self.ctx.scheduler.status_text())

    def _selected_with(self, *statuses: TargetStatus) -> list[int]:
        return [i for i in selected_ids(self.table) if self._statuses.get(i) in statuses]

    def _update_buttons(self) -> None:
        self.now_btn.setEnabled(bool(self._selected_with(S.SCHEDULED)))
        self.reschedule_btn.setEnabled(bool(self._selected_with(S.SCHEDULED)))
        self.unschedule_btn.setEnabled(bool(self._selected_with(S.SCHEDULED)))
        self.retry_btn.setEnabled(bool(self._selected_with(S.FAILED, S.NEEDS_ATTENTION)))
        self.open_btn.setEnabled(any(i in self._links for i in selected_ids(self.table)))

    def _update_targets(self, ids: list[int], fn) -> None:
        with self.ctx.db.session() as s:
            for target_id in ids:
                fn(s.get(PostTarget, target_id))
            s.commit()
        self.on_show()

    def _post_now(self) -> None:
        now = utcnow()

        def set_now(t: PostTarget) -> None:
            t.scheduled_at = now

        self._update_targets(self._selected_with(S.SCHEDULED), set_now)
        self.ctx.scheduler.tick()
        self.on_show()

    def _reschedule(self) -> None:
        ids = self._selected_with(S.SCHEDULED)
        with self.ctx.db.session() as s:
            first = s.get(PostTarget, ids[0]).scheduled_at
        initial = utc_to_local(first) if first else default_post_time()
        chosen = ask_datetime(self, "Đổi giờ đăng", initial)
        if chosen is None:
            return
        when = local_to_utc(chosen)

        def set_when(t: PostTarget) -> None:
            t.scheduled_at = when

        self._update_targets(ids, set_when)

    def _unschedule(self) -> None:
        self._update_targets(self._selected_with(S.SCHEDULED), posting.unschedule)
        self.window().statusBar().showMessage("Đã đưa về trang Chờ duyệt.", 5000)

    def _retry(self) -> None:
        now = utcnow()
        self._update_targets(self._selected_with(S.FAILED, S.NEEDS_ATTENTION), lambda t: posting.retry(t, now))
        self.ctx.scheduler.tick()
        self.on_show()

    def _open_links(self) -> None:
        for i in selected_ids(self.table):
            if i in self._links:
                QDesktopServices.openUrl(QUrl(self._links[i]))
