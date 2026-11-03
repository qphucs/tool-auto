from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__
from app.core.context import AppContext
from app.ui.pages.accounts import AccountsPage
from app.ui.pages.base import Page
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.logs import LogsPage
from app.ui.pages.editor import EditorPage
from app.ui.pages.review import ReviewPage
from app.ui.pages.schedule import SchedulePage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.templates import TemplatesPage

PAGES: tuple[type[Page], ...] = (
    EditorPage,
    TemplatesPage,
    DashboardPage,
    AccountsPage,
    ReviewPage,
    SchedulePage,
    LogsPage,
    SettingsPage,
)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1200, 760)
        self.setMinimumSize(960, 620)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.stack = QStackedWidget()
        self.pages: list[Page] = []
        for cls in PAGES:
            page = cls(ctx)
            self.pages.append(page)
            self.stack.addWidget(page)
            self.sidebar.addItem(cls.title)

        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        side = QWidget()
        side.setFixedWidth(220)
        side.setStyleSheet("background: #1e2330;")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)
        side_layout.addWidget(brand)
        side_layout.addWidget(self.sidebar, 1)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(side)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.sidebar.currentRowChanged.connect(self._show_page)
        self.sidebar.setCurrentRow(0)
        self.statusBar().showMessage(f"Dữ liệu: {ctx.settings.data_dir}")
        ctx.scheduler.changed.connect(self._refresh_current)
        ctx.scheduler.message.connect(lambda text: self.statusBar().showMessage(text, 15_000))

    def _show_page(self, row: int) -> None:
        if 0 <= row < len(self.pages):
            self.stack.setCurrentIndex(row)
            self.pages[row].on_show()

    def _refresh_current(self) -> None:
        self.pages[self.stack.currentIndex()].on_show()

    def start_background(self) -> None:
        """Gọi sau khi cửa sổ đã hiện: xử lý bài dở dang, bài quá giờ rồi bật lịch đăng."""
        scheduler = self.ctx.scheduler
        interrupted = scheduler.recover()
        if interrupted:
            QMessageBox.warning(
                self,
                APP_NAME,
                f"Có {interrupted} video đang đăng dở khi app bị tắt.\n"
                "Xem ở trang Lịch đăng > Lỗi / cần xử lý và kiểm tra trên nền tảng xem video đã lên chưa.",
            )
        overdue = scheduler.overdue_count()
        if overdue:
            answer = QMessageBox.question(
                self,
                APP_NAME,
                f"Có {overdue} video đã quá giờ đăng trong lúc app tắt.\n\n"
                "Đăng bù ngay bây giờ? (Chọn No để đưa chúng về trang Chờ duyệt.)",
            )
            if answer != QMessageBox.StandardButton.Yes:
                scheduler.send_overdue_back()
        scheduler.start()
        self._refresh_current()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.ctx.media.running:
            answer = QMessageBox.question(
                self, APP_NAME, "Đang phân tích hoặc dựng video. Thoát bây giờ sẽ hủy việc đó.\n\nVẫn thoát?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.ctx.media.cancel(wait=5)
        if self.ctx.scheduler.is_posting:
            answer = QMessageBox.question(
                self,
                APP_NAME,
                "Đang đăng một video. Thoát bây giờ sẽ dừng giữa chừng.\n\nVẫn thoát?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
