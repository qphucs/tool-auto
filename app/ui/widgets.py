from datetime import datetime, timedelta

from PySide6.QtCore import QDateTime, QItemSelectionModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

ID_ROLE = Qt.ItemDataRole.UserRole


def make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(True)
    return table


def fill_table(table: QTableWidget, rows: list[tuple[int, list[str]]]) -> None:
    """Đổ dữ liệu vào bảng, giữ nguyên các dòng đang chọn. Mỗi dòng: (id, [các ô])."""
    keep = set(selected_ids(table))
    table.blockSignals(True)
    table.clearSelection()
    table.setRowCount(len(rows))
    for r, (row_id, cells) in enumerate(rows):
        for c, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            if c == 0:
                item.setData(ID_ROLE, row_id)
            table.setItem(r, c, item)
    selection = table.selectionModel()
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    for r, (row_id, _) in enumerate(rows):
        if row_id in keep:
            selection.select(table.model().index(r, 0), flags)
    table.blockSignals(False)
    table.itemSelectionChanged.emit()


def selected_ids(table: QTableWidget) -> list[int]:
    rows = sorted({i.row() for i in table.selectionModel().selectedRows()})
    return [table.item(r, 0).data(ID_ROLE) for r in rows if table.item(r, 0)]


def datetime_edit(initial: datetime) -> QDateTimeEdit:
    edit = QDateTimeEdit(QDateTime(initial))
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd/MM/yyyy HH:mm")
    return edit


def default_post_time() -> datetime:
    """1 tiếng nữa, làm tròn lên 5 phút."""
    t = datetime.now().replace(second=0, microsecond=0) + timedelta(hours=1)
    return t + timedelta(minutes=(5 - t.minute % 5) % 5)


def ask_datetime(parent: QWidget, title: str, initial: datetime) -> datetime | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    edit = datetime_edit(initial)
    layout.addWidget(edit)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return edit.dateTime().toPython()
