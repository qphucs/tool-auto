from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
)
from sqlalchemy import select

from app.core.context import AppContext
from app.core.media import VideoInfo, probe
from app.core.models import (
    ACCOUNT_STATUS_LABELS,
    PLATFORM_LABELS,
    Account,
    AccountStatus,
    Post,
    PostTarget,
    TargetStatus,
    Video,
)
from app.core.timeutil import local_to_utc
from app.uploaders import UPLOADERS, get_uploader
from app.uploaders.base import VISIBILITY_LABELS, parse_hashtags
from app.ui.widgets import datetime_edit, default_post_time

VIDEO_FILTER = "Video (*.mp4 *.mov *.mkv *.webm *.avi *.m4v)"


def visibility_combo() -> QComboBox:
    combo = QComboBox()
    for key, label in VISIBILITY_LABELS.items():
        combo.addItem(label, key)
    return combo


class ComposeDialog(QDialog):
    """Chọn video + tài khoản + nội dung, rồi đưa vào hàng chờ duyệt."""

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.created = 0
        self._info = VideoInfo()
        self.setWindowTitle("Tạo bài đăng")
        self.setMinimumSize(620, 640)
        form = QFormLayout(self)

        self.video_path = QLineEdit()
        self.video_path.setReadOnly(True)
        self.video_path.setPlaceholderText("Chưa chọn video")
        browse = QPushButton("Chọn video...")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.video_path, 1)
        row.addWidget(browse)
        form.addRow("Video", row)
        self.video_info = QLabel()
        self.video_info.setObjectName("muted")
        form.addRow("", self.video_info)

        self.accounts = QListWidget()
        self.accounts.setMaximumHeight(140)
        self._load_accounts()
        form.addRow("Đăng lên", self.accounts)

        self.title_edit = QLineEdit()
        self.description = QPlainTextEdit()
        self.description.setMinimumHeight(120)
        self.hashtags = QLineEdit()
        self.hashtags.setPlaceholderText("#tag1 #tag2")
        self.visibility = visibility_combo()
        self.when = datetime_edit(default_post_time())
        form.addRow("Tiêu đề", self.title_edit)
        form.addRow("Mô tả", self.description)
        form.addRow("Hashtag", self.hashtags)
        form.addRow("Chế độ hiển thị", self.visibility)
        form.addRow("Giờ đăng", self.when)
        note = QLabel("Sau khi tạo, bài sẽ nằm ở trang Chờ duyệt. Bạn có thể sửa nội dung riêng cho từng tài khoản ở đó.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Đưa vào chờ duyệt")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _load_accounts(self) -> None:
        with self.ctx.db.session() as s:
            accounts = s.scalars(
                select(Account).where(Account.platform.in_(list(UPLOADERS))).order_by(Account.platform, Account.name)
            ).all()
        for a in accounts:
            text = f"{PLATFORM_LABELS[a.platform]} · {a.name}"
            if a.status != AccountStatus.ACTIVE:
                text += f"  ({ACCOUNT_STATUS_LABELS[a.status]})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, a.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.accounts.addItem(item)
        if not accounts:
            self.accounts.addItem("Chưa có tài khoản. Hãy thêm ở trang Tài khoản trước.")

    def set_video(self, path: Path) -> None:
        self.video_path.setText(str(path))
        self._info = probe(path)
        self.video_info.setText(self._info.describe())
        if not self.title_edit.text().strip():
            self.title_edit.setText(path.stem)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn video", "", VIDEO_FILTER)
        if path:
            self.set_video(Path(path))

    def checked_account_ids(self) -> list[int]:
        ids = []
        for i in range(self.accounts.count()):
            item = self.accounts.item(i)
            if item.data(Qt.ItemDataRole.UserRole) is not None and item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def accept(self) -> None:
        path = Path(self.video_path.text()) if self.video_path.text() else None
        account_ids = self.checked_account_ids()
        title = self.title_edit.text().strip()
        description = self.description.toPlainText()
        hashtags = self.hashtags.text().strip()

        problems = []
        if path is None or not path.is_file():
            problems.append("Hãy chọn file video.")
        if not account_ids:
            problems.append("Hãy chọn ít nhất một tài khoản.")
        with self.ctx.db.session() as s:
            platforms = {s.get(Account, i).platform for i in account_ids}
        for p in platforms:
            problems += [f"{PLATFORM_LABELS[p]}: {x}" for x in get_uploader(p).validate(title, description, parse_hashtags(hashtags))]
        if problems:
            QMessageBox.warning(self, "Tạo bài đăng", "\n".join(problems))
            return

        scheduled_at = local_to_utc(self.when.dateTime().toPython())
        with self.ctx.db.session() as s:
            video = Video(
                file_path=str(path),
                title=path.stem,
                duration_sec=self._info.duration,
                width=self._info.width,
                height=self._info.height,
            )
            post = Post(video=video)
            for account_id in account_ids:
                post.targets.append(
                    PostTarget(
                        account_id=account_id,
                        title=title,
                        description=description,
                        hashtags=hashtags,
                        visibility=self.visibility.currentData(),
                        scheduled_at=scheduled_at,
                        status=TargetStatus.PENDING_REVIEW,
                    )
                )
            s.add(post)
            s.commit()
        self.created = len(account_ids)
        super().accept()
