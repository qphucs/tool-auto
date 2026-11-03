import logging
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, __version__
from app.core import paths
from app.core.database import Database
from app.core.logging_setup import setup_logging
from app.core.settings import load_settings, save_settings, settings_path
from app.ui.main_window import MainWindow
from app.ui.services import create_context
from app.ui.theme import STYLESHEET

log = logging.getLogger(__name__)


def _install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        log.critical("Lỗi không mong muốn", exc_info=(exc_type, exc, tb))
        if QApplication.instance():
            detail = "".join(traceback.format_exception_only(exc_type, exc)).strip()
            QMessageBox.critical(None, APP_NAME, f"Có lỗi xảy ra:\n{detail}\n\nChi tiết đã ghi vào nhật ký.")

    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    # Giao diện được thiết kế cho nền sáng; không theo chế độ tối của Windows để hộp thoại không bị chữ tối trên nền tối
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    app.setStyleSheet(STYLESHEET)

    first_run = not settings_path().exists()
    settings = load_settings()
    try:
        paths.ensure_data_dirs(settings.data_path)
    except OSError as e:
        QMessageBox.critical(
            None,
            APP_NAME,
            f"Không tạo được thư mục dữ liệu:\n{settings.data_dir}\n\n{e}\n\n"
            f"Hãy sửa \"data_dir\" trong file:\n{settings_path()}",
        )
        return 1
    if first_run:
        save_settings(settings)

    setup_logging(settings.logs_dir)
    _install_excepthook()
    log.info("Khởi động %s %s, dữ liệu tại %s", APP_NAME, __version__, settings.data_dir)

    db = Database(settings.db_path)
    ctx = create_context(settings, db)
    window = MainWindow(ctx)
    window.show()
    window.start_background()
    code = app.exec()
    ctx.media.cancel(wait=5)
    ctx.scheduler.stop()
    ctx.worker.stop()
    db.close()
    log.info("Thoát app")
    return code
