import json

from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton
from sqlalchemy import select

from app.core.context import AppContext
from app.core.models import StyleTemplate
from app.core.timeutil import fmt_local
from app.editor.template import FRAMING_LABELS, TemplateSpec
from app.ui.pages.base import Page
from app.ui.widgets import fill_table, make_table, selected_ids


class TemplatesPage(Page):
    title = "Mẫu phong cách"
    subtitle = "Các mẫu đã lưu từ trang Dựng video. Chọn lại ở mục \"mẫu đã lưu\" để dựng không cần phân tích lại."
    HEADERS = ["Tên", "Kích thước", "Khung hình", "Số cảnh", "Nhịp TB", "Thời lượng", "Ngày tạo"]

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        bar = QHBoxLayout()
        self.rename_btn = QPushButton("Đổi tên")
        self.delete_btn = QPushButton("Xóa")
        bar.addWidget(self.rename_btn)
        bar.addWidget(self.delete_btn)
        bar.addStretch(1)
        self.body.addLayout(bar)
        self.table = make_table(self.HEADERS)
        self.table.setColumnWidth(0, 220)
        self.body.addWidget(self.table, 1)
        self.detail = QLabel()
        self.detail.setObjectName("muted")
        self.detail.setWordWrap(True)
        self.body.addWidget(self.detail)

        self.rename_btn.clicked.connect(self._rename)
        self.delete_btn.clicked.connect(self._delete)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self._specs: dict[int, TemplateSpec] = {}
        self._on_selection()

    def on_show(self) -> None:
        rows = []
        self._specs = {}
        with self.ctx.db.session() as s:
            for t in s.scalars(select(StyleTemplate).order_by(StyleTemplate.name)):
                spec = TemplateSpec.from_dict(json.loads(t.spec_json))
                self._specs[t.id] = spec
                shots = spec.shot_durations
                avg = f"{sum(shots) / len(shots):.1f} giây" if shots else ""
                rows.append(
                    (
                        t.id,
                        [
                            t.name,
                            f"{spec.width}x{spec.height}",
                            FRAMING_LABELS.get(spec.framing, spec.framing),
                            str(len(shots)),
                            avg,
                            f"{spec.duration:.1f} giây",
                            fmt_local(t.created_at),
                        ],
                    )
                )
        fill_table(self.table, rows)

    def _on_selection(self) -> None:
        ids = selected_ids(self.table)
        self.rename_btn.setEnabled(len(ids) == 1)
        self.delete_btn.setEnabled(bool(ids))
        spec = self._specs.get(ids[0]) if len(ids) == 1 else None
        self.detail.setText(f"{spec.summary()}\nVideo mẫu: {spec.sample_file}" if spec else "")

    def _rename(self) -> None:
        [template_id] = selected_ids(self.table)
        with self.ctx.db.session() as s:
            t = s.get(StyleTemplate, template_id)
            name, ok = QInputDialog.getText(self, "Đổi tên mẫu", "Tên mới:", text=t.name)
            if ok and name.strip():
                t.name = name.strip()
                s.commit()
        self.on_show()

    def _delete(self) -> None:
        ids = selected_ids(self.table)
        if QMessageBox.question(self, "Xóa mẫu", f"Xóa {len(ids)} mẫu phong cách?") != QMessageBox.StandardButton.Yes:
            return
        with self.ctx.db.session() as s:
            for template_id in ids:
                s.delete(s.get(StyleTemplate, template_id))
            s.commit()
        self.on_show()
