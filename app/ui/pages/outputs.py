from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QPushButton
from sqlalchemy import select

from app.core.context import AppContext
from app.core.media import probe
from app.core.models import Clip
from app.core.timeutil import fmt_local
from app.ui.pages.base import Page
from app.ui.widgets import fill_table, make_table, selected_ids


class OutputsPage(Page):
    title = "Thành phẩm"
    subtitle = "Các video đã dựng bản cuối 1080x1920. Bấm đúp để xem."
    HEADERS = ["Video", "Từ video gốc", "Thời lượng", "Ngày dựng", "File"]

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        bar = QHBoxLayout()
        self.open_btn = QPushButton("Xem video")
        self.open_btn.setObjectName("primary")
        folder = QPushButton("Mở thư mục thành phẩm")
        bar.addWidget(self.open_btn)
        bar.addWidget(folder)
        bar.addStretch(1)
        self.body.addLayout(bar)
        self.table = make_table(self.HEADERS)
        for col, width in enumerate((260, 200, 90, 130)):
            self.table.setColumnWidth(col, width)
        self.body.addWidget(self.table, 1)
        self._paths: dict[int, str] = {}

        self.open_btn.clicked.connect(self._open)
        self.table.itemDoubleClicked.connect(lambda _: self._open())
        folder.clicked.connect(self._open_folder)

    def on_show(self) -> None:
        rows = []
        with self.ctx.db.session() as s:
            for c in s.scalars(select(Clip).where(Clip.final_path != "").order_by(Clip.updated_at.desc())):
                path = Path(c.final_path)
                if not path.is_file():
                    continue
                duration = probe(path).duration or 0
                self._paths[c.id] = str(path)
                rows.append((c.id, [c.title, c.project.name, f"{duration:.0f} giây", fmt_local(c.updated_at), path.name]))
        fill_table(self.table, rows)

    def _open(self) -> None:
        for clip_id in selected_ids(self.table)[:1]:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._paths[clip_id]))

    def _open_folder(self) -> None:
        folder = self.ctx.settings.outputs_dir
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
