from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

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
