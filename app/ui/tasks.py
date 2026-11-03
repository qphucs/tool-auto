import logging
import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from app.editor.ffmpeg import Cancelled

log = logging.getLogger(__name__)

# fn(report, cancel) -> kết quả; report(tỉ lệ 0-1, thông báo)
TaskFn = Callable[[Callable[[float, str], None], threading.Event], Any]


class BackgroundTask(QObject):
    """Chạy một việc nặng (phân tích, dựng video) ở luồng nền, mỗi lúc một việc."""

    started = Signal(str)  # tên việc
    progress = Signal(float, str)
    finished = Signal(str, object, object)  # tên việc, kết quả, lỗi

    def __init__(self):
        super().__init__()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._running = False

    @property
    def running(self) -> bool:
        # Dùng cờ riêng: khi tín hiệu finished tới giao diện, luồng có thể chưa kịp kết thúc hẳn
        return self._running

    def start(self, kind: str, fn: TaskFn) -> None:
        if self._running:
            raise RuntimeError("Đang có việc khác chạy")
        self._running = True
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(kind, fn, self._cancel), daemon=True)
        self.started.emit(kind)
        self._thread.start()

    def cancel(self, wait: float = 0) -> None:
        self._cancel.set()
        if wait and self._thread:
            self._thread.join(wait)

    def _run(self, kind: str, fn: TaskFn, cancel: threading.Event) -> None:
        result, error = None, None
        try:
            result = fn(self.progress.emit, cancel)
        except Exception as e:
            if not isinstance(e, Cancelled):
                log.exception("Việc %s thất bại", kind)
            error = e
        self._running = False
        self.finished.emit(kind, result, error)
