import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from app.automation.browser import open_login_window


class LoginWindows(QObject):
    """Theo dõi các cửa sổ Chrome đăng nhập đang mở, báo khi người dùng đóng chúng."""

    closed = Signal(int)  # account_id

    def __init__(self):
        super().__init__()
        self._procs: dict[int, subprocess.Popen] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._poll)

    def open(self, account_id: int, profile_dir: Path, url: str) -> None:
        if self.is_open(account_id):
            return
        self._procs[account_id] = open_login_window(profile_dir, url)
        self._timer.start()

    def is_open(self, account_id: int) -> bool:
        proc = self._procs.get(account_id)
        return proc is not None and proc.poll() is None

    def open_ids(self) -> set[int]:
        return {i for i in self._procs if self.is_open(i)}

    def _poll(self) -> None:
        for account_id, proc in list(self._procs.items()):
            if proc.poll() is not None:
                del self._procs[account_id]
                self.closed.emit(account_id)
        if not self._procs:
            self._timer.stop()
