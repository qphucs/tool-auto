import logging
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
)
from sqlalchemy import select

from app.automation.browser import BrowserNotFound
from app.automation.worker import Job
from app.core.context import AppContext
from app.core.models import (
    ACCOUNT_STATUS_LABELS,
    PLATFORM_LABELS,
    Account,
    AccountStatus,
    Platform,
    TargetStatus,
    utcnow,
)
from app.core.timeutil import fmt_local
from app.uploaders import UPLOADERS, get_uploader
from app.ui.pages.base import Page
from app.ui.widgets import fill_table, make_table, selected_ids

log = logging.getLogger(__name__)


class AccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thêm tài khoản")
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        self.platform = QComboBox()
        for p in Platform:
            supported = p in UPLOADERS
            self.platform.addItem(PLATFORM_LABELS[p] + ("" if supported else " (GĐ2)"), p)
            if not supported:
                self.platform.model().item(self.platform.count() - 1).setEnabled(False)
        self.name = QLineEdit()
        self.name.setPlaceholderText("VD: Kênh nấu ăn chính")
        self.group = QLineEdit()
        self.group.setPlaceholderText("Không bắt buộc")
        self.notes = QLineEdit()
        form.addRow("Nền tảng", self.platform)
        form.addRow("Tên gợi nhớ", self.name)
        form.addRow("Nhóm", self.group)
        form.addRow("Ghi chú", self.notes)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Thêm tài khoản", "Hãy nhập tên gợi nhớ cho tài khoản.")
            return
        super().accept()


class AccountsPage(Page):
    title = "Tài khoản"
    subtitle = (
        "Mỗi tài khoản có một hồ sơ Chrome riêng. Bấm Đăng nhập, đăng nhập trong cửa sổ Chrome vừa mở "
        "rồi đóng cửa sổ đó, tool sẽ tự kiểm tra."
    )
    HEADERS = ["Nền tảng", "Tên", "Nhóm", "Trạng thái", "Kiểm tra lần cuối", "Ghi chú"]

    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self._checking: set[int] = set()

        bar = QHBoxLayout()
        self.add_btn = QPushButton("+ Thêm tài khoản")
        self.add_btn.setObjectName("primary")
        self.login_btn = QPushButton("Đăng nhập")
        self.check_btn = QPushButton("Kiểm tra đăng nhập")
        self.delete_btn = QPushButton("Xóa")
        for b in (self.add_btn, self.login_btn, self.check_btn, self.delete_btn):
            bar.addWidget(b)
        bar.addStretch(1)
        self.body.addLayout(bar)

        self.table = make_table(self.HEADERS)
        self.table.setColumnWidth(0, 130)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(3, 170)
        self.table.setColumnWidth(4, 140)
        self.body.addWidget(self.table, 1)

        self.add_btn.clicked.connect(self._add)
        self.login_btn.clicked.connect(self._login_selected)
        self.check_btn.clicked.connect(lambda: self._check(selected_ids(self.table)))
        self.delete_btn.clicked.connect(self._delete)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        ctx.worker.finished.connect(self._on_job_finished)
        ctx.logins.closed.connect(lambda account_id: self._check([account_id]))
        self._update_buttons()

    def on_show(self) -> None:
        with self.ctx.db.session() as s:
            accounts = s.scalars(select(Account).order_by(Account.platform, Account.name)).all()
        rows = []
        for a in accounts:
            if a.id in self._checking:
                status = "Đang kiểm tra..."
            elif self.ctx.logins.is_open(a.id):
                status = "Đang mở cửa sổ đăng nhập"
            else:
                status = ACCOUNT_STATUS_LABELS[a.status]
            rows.append(
                (a.id, [PLATFORM_LABELS[a.platform], a.name, a.group_name, status, fmt_local(a.last_checked_at), a.notes])
            )
        fill_table(self.table, rows)

    def _update_buttons(self) -> None:
        n = len(selected_ids(self.table))
        self.login_btn.setEnabled(n == 1)
        self.check_btn.setEnabled(n >= 1)
        self.delete_btn.setEnabled(n >= 1)

    def _status(self, text: str) -> None:
        self.window().statusBar().showMessage(text, 10_000)

    # ----- thêm / đăng nhập -----

    def _add(self) -> None:
        dialog = AccountDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        with self.ctx.db.session() as s:
            acc = Account(
                # Qt trả enum về dạng chuỗi, phải đổi lại thành Platform
                platform=Platform(dialog.platform.currentData()),
                name=dialog.name.text().strip(),
                group_name=dialog.group.text().strip(),
                notes=dialog.notes.text().strip(),
            )
            s.add(acc)
            s.flush()
            acc.profile_dir = str(self.ctx.settings.data_path / "profiles" / f"{acc.platform.value}-{acc.id}")
            s.commit()
            account_id = acc.id
        log.info("Thêm tài khoản #%s", account_id)
        self.on_show()
        answer = QMessageBox.question(self, "Thêm tài khoản", "Mở Chrome để đăng nhập tài khoản này ngay?")
        if answer == QMessageBox.StandardButton.Yes:
            self._open_login(account_id)

    def _login_selected(self) -> None:
        ids = selected_ids(self.table)
        if len(ids) == 1:
            self._open_login(ids[0])

    def _open_login(self, account_id: int) -> None:
        if self.ctx.scheduler.posting_account_id == account_id:
            QMessageBox.information(self, "Đăng nhập", "Tài khoản này đang đăng video. Hãy chờ đăng xong.")
            return
        with self.ctx.db.session() as s:
            acc = s.get(Account, account_id)
            profile, platform = Path(acc.profile_dir), acc.platform
        try:
            self.ctx.logins.open(account_id, profile, get_uploader(platform).login_url)
        except BrowserNotFound as e:
            QMessageBox.warning(self, "Đăng nhập", str(e))
            return
        self.on_show()
        QMessageBox.information(
            self,
            "Đăng nhập",
            "Đã mở Chrome riêng cho tài khoản này.\n\n"
            "1. Đăng nhập trong cửa sổ đó (kể cả xác minh 2 bước nếu có).\n"
            "2. Khi đã vào được trang của bạn, đóng hẳn cửa sổ Chrome đó.\n\n"
            "Tool sẽ tự kiểm tra đăng nhập sau khi bạn đóng cửa sổ.",
        )

    # ----- kiểm tra đăng nhập -----

    def _check(self, ids: list[int]) -> None:
        with self.ctx.db.session() as s:
            for account_id in ids:
                if account_id in self._checking or self.ctx.logins.is_open(account_id):
                    continue
                acc = s.get(Account, account_id)
                uploader = get_uploader(acc.platform) if acc else None
                if uploader is None:
                    continue
                profile = Path(acc.profile_dir)
                self._checking.add(account_id)
                self.ctx.worker.submit(
                    Job(
                        "check_login",
                        lambda pw, u=uploader, p=profile: u.check_login(pw, p, headless=True),
                        payload=account_id,
                    )
                )
        self._status("Đang kiểm tra đăng nhập...")
        self.on_show()

    def _on_job_finished(self, job: Job, result, error) -> None:
        if job.kind != "check_login":
            return
        self._checking.discard(job.payload)
        with self.ctx.db.session() as s:
            acc = s.get(Account, job.payload)
            if acc is None:
                return
            acc.last_checked_at = utcnow()
            if error is not None:
                acc.status = AccountStatus.ERROR
                self._status(f"{acc.name}: lỗi khi kiểm tra ({error})")
            else:
                acc.status = AccountStatus.ACTIVE if result else AccountStatus.EXPIRED
                self._status(f"{acc.name}: {ACCOUNT_STATUS_LABELS[acc.status]}")
            s.commit()
        if self.isVisible():
            self.on_show()

    # ----- xóa -----

    def _delete(self) -> None:
        ids = selected_ids(self.table)
        answer = QMessageBox.question(
            self,
            "Xóa tài khoản",
            f"Xóa {len(ids)} tài khoản khỏi tool?\n\n"
            "Hồ sơ Chrome (phiên đăng nhập) và lịch sử đăng của các tài khoản này cũng bị xóa. "
            "Tài khoản thật trên nền tảng không bị ảnh hưởng.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        busy = {TargetStatus.SCHEDULED, TargetStatus.POSTING}
        blocked, profiles = [], []
        with self.ctx.db.session() as s:
            for account_id in ids:
                acc = s.get(Account, account_id)
                if acc is None:
                    continue
                if self.ctx.logins.is_open(acc.id) or any(t.status in busy for t in acc.targets):
                    blocked.append(acc.name)
                    continue
                profiles.append(acc.profile_dir)
                s.delete(acc)
            s.commit()
        for p in profiles:
            if p:
                shutil.rmtree(p, ignore_errors=True)
        self.on_show()
        if blocked:
            QMessageBox.information(
                self,
                "Xóa tài khoản",
                "Chưa xóa được (đang có bài lên lịch, đang đăng hoặc đang mở cửa sổ đăng nhập):\n"
                + "\n".join(blocked),
            )
