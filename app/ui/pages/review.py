from pathlib import Path

from PySide6.QtCore import QDateTime, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from app.core import posting
from app.core.context import AppContext
from app.core.models import PLATFORM_LABELS, PostTarget, TargetStatus, utcnow
from app.core.timeutil import fmt_local, local_to_utc, utc_to_local
from app.uploaders.base import VISIBILITY_LABELS
from app.uploaders.youtube import TITLE_MAX
from app.ui.compose_dialog import ComposeDialog, visibility_combo
from app.ui.pages.base import Page
from app.ui.widgets import datetime_edit, default_post_time, fill_table, make_table, selected_ids

FILTERS = (("Chờ duyệt", TargetStatus.PENDING_REVIEW), ("Đã từ chối", TargetStatus.REJECTED))


class ReviewPage(Page):
    title = "Chờ duyệt"
    subtitle = "Video chỉ được đăng sau khi bạn duyệt. Chọn một dòng để xem và sửa nội dung."
    HEADERS = ["Video", "Tài khoản", "Tiêu đề", "Giờ đăng", "Hiển thị"]

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self._editing_id: int | None = None
        self._loaded_values: tuple = ()

        bar = QHBoxLayout()
        self.new_btn = QPushButton("+ Tạo bài đăng")
        self.new_btn.setObjectName("primary")
        self.filter = QComboBox()
        for label, status in FILTERS:
            self.filter.addItem(label, status)
        self.approve_btn = QPushButton("Duyệt")
        self.reject_btn = QPushButton("Từ chối")
        self.restore_btn = QPushButton("Đưa về chờ duyệt")
        self.delete_btn = QPushButton("Xóa")
        for w in (self.new_btn, self.filter, self.approve_btn, self.reject_btn, self.restore_btn, self.delete_btn):
            bar.addWidget(w)
        bar.addStretch(1)
        self.body.addLayout(bar)

        self.table = make_table(self.HEADERS)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 120)
        splitter = QSplitter()
        splitter.addWidget(self.table)
        splitter.addWidget(self._build_editor())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.body.addWidget(splitter, 1)

        self.new_btn.clicked.connect(self._new_post)
        self.filter.currentIndexChanged.connect(self.on_show)
        self.approve_btn.clicked.connect(self._approve)
        self.reject_btn.clicked.connect(lambda: self._set_status(TargetStatus.REJECTED))
        self.restore_btn.clicked.connect(lambda: self._set_status(TargetStatus.PENDING_REVIEW))
        self.delete_btn.clicked.connect(self._delete)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self._on_selection()

    def _build_editor(self) -> QWidget:
        self.editor = QGroupBox("Nội dung đăng")
        form = QFormLayout(self.editor)
        self.e_account = QLabel()
        self.e_title = QLineEdit()
        self.e_title_count = QLabel()
        self.e_title_count.setObjectName("muted")
        self.e_title.textChanged.connect(lambda t: self.e_title_count.setText(f"{len(t)}/{TITLE_MAX} ký tự"))
        self.e_description = QPlainTextEdit()
        self.e_hashtags = QLineEdit()
        self.e_hashtags.setPlaceholderText("#tag1 #tag2")
        self.e_visibility = visibility_combo()
        self.e_when = datetime_edit(default_post_time())
        self.e_problems = QLabel()
        self.e_problems.setWordWrap(True)
        self.e_problems.setStyleSheet("color: #b91c1c;")
        form.addRow("Tài khoản", self.e_account)
        form.addRow("Tiêu đề", self.e_title)
        form.addRow("", self.e_title_count)
        form.addRow("Mô tả", self.e_description)
        form.addRow("Hashtag", self.e_hashtags)
        form.addRow("Hiển thị", self.e_visibility)
        form.addRow("Giờ đăng", self.e_when)
        form.addRow(self.e_problems)

        buttons = QHBoxLayout()
        self.save_btn = QPushButton("Lưu thay đổi")
        self.preview_btn = QPushButton("Xem video")
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.preview_btn)
        buttons.addStretch(1)
        form.addRow(buttons)
        self.save_btn.clicked.connect(lambda: self._save_editor(show_result=True))
        self.preview_btn.clicked.connect(self._preview)

        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.addWidget(self.editor)
        return wrapper

    def _current_filter(self) -> TargetStatus:
        return TargetStatus(self.filter.currentData())

    def on_show(self) -> None:
        status = self._current_filter()
        with self.ctx.db.session() as s:
            targets = s.scalars(
                select(PostTarget).where(PostTarget.status == status).order_by(PostTarget.scheduled_at, PostTarget.id)
            ).all()
            rows = [
                (
                    t.id,
                    [
                        Path(t.post.video.file_path).name,
                        f"{PLATFORM_LABELS[t.account.platform]} · {t.account.name}",
                        t.title,
                        fmt_local(t.scheduled_at),
                        VISIBILITY_LABELS.get(t.visibility, t.visibility),
                    ],
                )
                for t in targets
            ]
        fill_table(self.table, rows)
        pending = status == TargetStatus.PENDING_REVIEW
        self.approve_btn.setVisible(pending)
        self.reject_btn.setVisible(pending)
        self.restore_btn.setVisible(not pending)

    def _editor_values(self) -> tuple:
        return (
            self.e_title.text().strip(),
            self.e_description.toPlainText(),
            self.e_hashtags.text().strip(),
            self.e_visibility.currentData(),
            self.e_when.dateTime().toPython(),
        )

    def _on_selection(self) -> None:
        # Chuyển sang dòng khác thì tự lưu nội dung vừa sửa, không để mất
        if self._editing_id is not None and self._editor_values() != self._loaded_values:
            self._save_editor(refresh=False)
            QTimer.singleShot(0, self.on_show)
        ids = selected_ids(self.table)
        for b in (self.approve_btn, self.reject_btn, self.restore_btn, self.delete_btn):
            b.setEnabled(bool(ids))
        self._load_editor(ids[0] if len(ids) == 1 else None)

    def _load_editor(self, target_id: int | None) -> None:
        self._editing_id = target_id
        self.editor.setEnabled(target_id is not None)
        if target_id is None:
            self.e_account.setText("Chọn đúng một dòng để sửa")
            for w in (self.e_title, self.e_hashtags):
                w.clear()
            self.e_description.clear()
            self.e_problems.clear()
            return
        with self.ctx.db.session() as s:
            t = s.get(PostTarget, target_id)
            self.e_account.setText(f"{PLATFORM_LABELS[t.account.platform]} · {t.account.name}")
            self.e_title.setText(t.title)
            self.e_description.setPlainText(t.description)
            self.e_hashtags.setText(t.hashtags)
            self.e_visibility.setCurrentIndex(max(self.e_visibility.findData(t.visibility), 0))
            when = utc_to_local(t.scheduled_at) if t.scheduled_at else default_post_time()
            self.e_when.setDateTime(QDateTime(when))
            self.e_problems.setText("\n".join(posting.validate_target(t)))
        self._loaded_values = self._editor_values()

    def _save_editor(self, show_result: bool = False, refresh: bool = True) -> None:
        if self._editing_id is None:
            return
        with self.ctx.db.session() as s:
            t = s.get(PostTarget, self._editing_id)
            t.title = self.e_title.text().strip()
            t.description = self.e_description.toPlainText()
            t.hashtags = self.e_hashtags.text().strip()
            t.visibility = self.e_visibility.currentData()
            t.scheduled_at = local_to_utc(self.e_when.dateTime().toPython())
            problems = posting.validate_target(t)
            s.commit()
        self.e_problems.setText("\n".join(problems))
        self._loaded_values = self._editor_values()
        if refresh:
            self.on_show()
        if show_result:
            self.window().statusBar().showMessage("Đã lưu thay đổi.", 5000)

    def _preview(self) -> None:
        if self._editing_id is None:
            return
        with self.ctx.db.session() as s:
            path = s.get(PostTarget, self._editing_id).post.video.file_path
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _new_post(self) -> None:
        dialog = ComposeDialog(self.ctx, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.filter.setCurrentIndex(0)
            self.on_show()
            self.window().statusBar().showMessage(f"Đã tạo {dialog.created} bài chờ duyệt.", 5000)

    def _approve(self) -> None:
        ids = selected_ids(self.table)
        if self._editing_id in ids:
            self._save_editor(refresh=False)
        now = utcnow()
        approved, problems = 0, []
        with self.ctx.db.session() as s:
            for target_id in ids:
                t = s.get(PostTarget, target_id)
                issues = posting.approve(t, now)
                if issues:
                    problems.append(f"• {t.title or '(chưa có tiêu đề)'} – {t.account.name}: {' '.join(issues)}")
                else:
                    approved += 1
            s.commit()
        self.on_show()
        self.ctx.scheduler.tick()
        msg = f"Đã duyệt {approved} bài, đã chuyển sang Lịch đăng."
        if problems:
            msg += "\n\nChưa duyệt được:\n" + "\n".join(problems)
            QMessageBox.warning(self, "Duyệt", msg)
        else:
            self.window().statusBar().showMessage(msg, 8000)

    def _set_status(self, status: TargetStatus) -> None:
        with self.ctx.db.session() as s:
            for target_id in selected_ids(self.table):
                s.get(PostTarget, target_id).status = status
            s.commit()
        self.on_show()

    def _delete(self) -> None:
        ids = selected_ids(self.table)
        answer = QMessageBox.question(self, "Xóa", f"Xóa {len(ids)} bài khỏi hàng chờ? File video gốc không bị xóa.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        with self.ctx.db.session() as s:
            for target_id in ids:
                t = s.get(PostTarget, target_id)
                post = t.post
                s.delete(t)
                s.flush()
                if not post.targets:
                    s.delete(post)
            s.commit()
        self.on_show()
