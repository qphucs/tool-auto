import logging
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from app.automation.login_windows import LoginWindows
from app.automation.worker import AutomationWorker, Job
from app.core import posting
from app.core.database import Database
from app.core.models import PostTarget, TargetStatus, utcnow
from app.core.settings import Settings
from app.uploaders import get_uploader

log = logging.getLogger(__name__)

TICK_MS = 15_000


class PostScheduler(QObject):
    """Mỗi lượt kiểm tra lấy một bài đến giờ đăng và giao cho luồng nền."""

    changed = Signal()
    message = Signal(str)

    def __init__(self, settings: Settings, db: Database, worker: AutomationWorker, logins: LoginWindows):
        super().__init__()
        self.settings = settings
        self.db = db
        self.worker = worker
        self.logins = logins
        self._posting: tuple[int, int] | None = None  # (target_id, account_id)
        self._last_finished: datetime | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self.tick)
        worker.finished.connect(self._on_finished)

    @property
    def is_posting(self) -> bool:
        return self._posting is not None

    @property
    def posting_account_id(self) -> int | None:
        return self._posting[1] if self._posting else None

    def recover(self) -> int:
        with self.db.session() as s:
            n = posting.recover_interrupted(s)
            s.commit()
        return n

    def overdue_count(self) -> int:
        with self.db.session() as s:
            return len(posting.overdue(s, utcnow()))

    def send_overdue_back(self) -> int:
        with self.db.session() as s:
            targets = posting.overdue(s, utcnow())
            for t in targets:
                posting.unschedule(t)
            s.commit()
        return len(targets)

    def start(self) -> None:
        self._timer.start()
        QTimer.singleShot(0, self.tick)

    def stop(self) -> None:
        self._timer.stop()

    def gap_remaining(self, now: datetime | None = None) -> timedelta | None:
        if self._last_finished is None:
            return None
        left = self._last_finished + timedelta(minutes=self.settings.min_gap_minutes) - (now or utcnow())
        return left if left > timedelta(0) else None

    def status_text(self) -> str:
        if self._posting:
            return "Đang đăng một video..."
        left = self.gap_remaining()
        if left:
            return f"Đang nghỉ giữa hai lần đăng, còn {int(left.total_seconds() // 60) + 1} phút."
        return "Sẵn sàng đăng."

    def tick(self) -> None:
        if self._posting or self.gap_remaining():
            return
        with self.db.session() as s:
            t = posting.next_due(s, utcnow(), self.logins.open_ids())
            if t is None:
                return
            problems = posting.validate_target(t)
            if problems:
                t.status = TargetStatus.NEEDS_ATTENTION
                t.last_error = " ".join(problems)
                s.commit()
                self.changed.emit()
                return
            posting.start_posting(t)
            s.commit()
            req = posting.build_request(t, self.settings)
            uploader = get_uploader(t.account.platform)
            self._posting = (t.id, t.account_id)
            title = t.title

        log.info("Bắt đầu đăng #%s: %s", self._posting[0], title)
        self.worker.submit(Job("upload", lambda pw: uploader.upload(pw, req), payload=self._posting[0]))
        self.message.emit(f"Đang đăng: {title}")
        self.changed.emit()

    def _on_finished(self, job: Job, result, error) -> None:
        if job.kind != "upload":
            return
        now = utcnow()
        with self.db.session() as s:
            t = s.get(PostTarget, job.payload)
            if t is not None:
                if error is None:
                    posting.finish_success(t, result.url, now)
                    msg = f"Đã đăng xong: {t.title}"
                else:
                    posting.finish_error(t, error, now, self.settings.max_retries)
                    msg = f"Đăng lỗi: {t.title}. Xem trang Lịch đăng."
                s.commit()
                self.message.emit(msg)
        self._posting = None
        self._last_finished = now
        self.changed.emit()
