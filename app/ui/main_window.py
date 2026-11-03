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
from app.ui.pages.base import Page
from app.ui.pages.brand import BrandPage
from app.ui.pages.logs import LogsPage
from app.ui.pages.outputs import OutputsPage
from app.ui.pages.preview import PreviewPage
from app.ui.pages.projects import ProjectsPage
from app.ui.pages.scripts import ScriptsPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.taskbar import TaskBar

PAGES: tuple[type[Page], ...] = (
    ProjectsPage,
    ScriptsPage,
    PreviewPage,
    OutputsPage,
    BrandPage,
    SettingsPage,
    LogsPage,
)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1280, 800)
        self.setMinimumSize(1060, 660)

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
        side.setFixedWidth(200)
        side.setStyleSheet("background: #1e2330;")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)
        side_layout.addWidget(brand)
        side_layout.addWidget(self.sidebar, 1)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.stack, 1)
        main_layout.addWidget(TaskBar(ctx.media))

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(side)
        layout.addWidget(main, 1)
        self.setCentralWidget(root)

        self.sidebar.currentRowChanged.connect(self._show_page)
        self.sidebar.setCurrentRow(0)
        self.statusBar().showMessage(f"Dữ liệu: {ctx.settings.data_dir}")

    def _show_page(self, row: int) -> None:
        if 0 <= row < len(self.pages):
            self.stack.setCurrentIndex(row)
            self.pages[row].on_show()

    def page(self, cls: type[Page]) -> Page:
        return next(p for p in self.pages if isinstance(p, cls))

    def _switch(self, cls: type[Page]) -> Page:
        """Chuyển trang mà không gọi on_show (trang tự nạp theo tham số được truyền)."""
        page = self.page(cls)
        index = self.pages.index(page)
        self.sidebar.blockSignals(True)
        self.sidebar.setCurrentRow(index)
        self.sidebar.blockSignals(False)
        self.stack.setCurrentIndex(index)
        return page

    def open_scripts(self, project_id: int | None = None, clip_id: int | None = None, scene_index: int | None = None) -> None:
        self._switch(ScriptsPage).open(project_id=project_id, clip_id=clip_id, scene_index=scene_index)

    def open_preview(self, clip_id: int | None = None) -> None:
        self._switch(PreviewPage).open(clip_id=clip_id)

    def open_brand(self) -> None:
        self._switch(BrandPage).on_show()

    def closeEvent(self, event: QCloseEvent) -> None:
        scripts = self.page(ScriptsPage)
        scripts._autosave()
        if self.ctx.media.running:
            answer = QMessageBox.question(
                self, APP_NAME, "Đang có việc chạy nền. Thoát bây giờ sẽ hủy việc đó.\n\nVẫn thoát?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.ctx.media.cancel(wait=5)
        event.accept()
