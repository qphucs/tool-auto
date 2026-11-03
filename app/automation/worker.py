"""Một luồng nền duy nhất chạy mọi việc dùng trình duyệt, lần lượt từng việc.

Playwright (sync) phải chạy trên cùng một luồng, và chạy lần lượt cũng đảm bảo
không bao giờ có hai video được đăng cùng lúc.
"""

import logging
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from playwright.sync_api import Playwright, sync_playwright
from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


@dataclass
class Job:
    kind: str
    fn: Callable[[Playwright], Any]
    payload: Any = None
    label: str = field(default="")


class AutomationWorker(QObject):
    # job, kết quả, lỗi (một trong hai là None). Phát từ luồng nền, Qt tự chuyển về luồng giao diện.
    finished = Signal(object, object, object)

    def __init__(self):
        super().__init__()
        self._queue: queue.Queue[Job | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._pending = 0
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._pending > 0

    def submit(self, job: Job) -> None:
        with self._lock:
            self._pending += 1
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="automation", daemon=True)
            self._thread.start()
        self._queue.put(job)

    def stop(self, timeout: float = 3.0) -> None:
        if self._thread and self._thread.is_alive():
            self._queue.put(None)
            self._thread.join(timeout)

    def _run(self) -> None:
        pw: Playwright | None = None
        try:
            while True:
                job = self._queue.get()
                if job is None:
                    break
                result, error = None, None
                try:
                    if pw is None:
                        pw = sync_playwright().start()
                    result = job.fn(pw)
                except Exception as e:  # mọi lỗi đều trả về giao diện, không làm chết luồng
                    log.exception("Việc %s thất bại", job.kind)
                    error = e
                finally:
                    with self._lock:
                        self._pending -= 1
                self.finished.emit(job, result, error)
        finally:
            if pw is not None:
                pw.stop()
