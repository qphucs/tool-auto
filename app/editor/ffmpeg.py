import shutil
import subprocess
import threading
from pathlib import Path

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class FFmpegError(Exception):
    pass


class Cancelled(Exception):
    pass


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise FFmpegError("Không tìm thấy FFmpeg. Hãy cài FFmpeg và thêm vào PATH.")
    return path


def check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def run(args: list[str], cwd: Path | None = None, cancel: threading.Event | None = None) -> tuple[str, str]:
    """Chạy ffmpeg, trả về (stdout, stderr). Dừng ngay nếu cancel được bật."""
    check_cancel(cancel)
    proc = subprocess.Popen(
        [ffmpeg_bin(), "-hide_banner", "-nostdin", *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )
    while True:
        try:
            out, err = proc.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                proc.kill()
                proc.communicate()
                raise Cancelled()
    if proc.returncode != 0:
        tail = "\n".join(err.strip().splitlines()[-6:])
        raise FFmpegError(f"FFmpeg báo lỗi:\n{tail}")
    return out, err
