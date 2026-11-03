from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.core.models import Account, AccountStatus, Platform, PostTarget, TargetStatus, utcnow
from app.core.settings import load_settings
from app.ui.compose_dialog import ComposeDialog
from app.ui.main_window import PAGES, MainWindow
from app.ui.pages.review import ReviewPage
from app.ui.pages.schedule import SchedulePage
from app.ui.pages.settings_page import SettingsPage


def _page(window, cls):
    return next(p for p in window.pages if isinstance(p, cls))


def _add_account(ctx, name="Kênh A") -> int:
    with ctx.db.session() as s:
        acc = Account(platform=Platform.YOUTUBE, name=name, status=AccountStatus.ACTIVE, profile_dir="x")
        s.add(acc)
        s.commit()
        return acc.id


def test_every_page_opens(ctx):
    window = MainWindow(ctx)
    assert window.sidebar.count() == len(PAGES)
    for row in range(window.sidebar.count()):
        window.sidebar.setCurrentRow(row)
        assert window.stack.currentIndex() == row
    window.close()


def test_settings_page_saves(ctx, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    window = MainWindow(ctx)
    page = _page(window, SettingsPage)
    page.min_gap.setValue(42)
    page.show_browser.setChecked(False)
    page.ai_provider.setCurrentIndex(page.ai_provider.findData("ollama"))
    page.ai_model.setText("qwen2.5vl:3b")
    page._save()

    saved = load_settings()
    assert saved.min_gap_minutes == 42
    assert saved.show_browser is False
    assert saved.ai.provider == "ollama"
    window.close()


def test_compose_review_approve(ctx, video_file, monkeypatch):
    acc_a = _add_account(ctx, "Kênh A")
    _add_account(ctx, "Kênh B")

    dialog = ComposeDialog(ctx)
    dialog.set_video(video_file)
    assert dialog.title_edit.text() == "clip"
    for i in range(dialog.accounts.count()):
        dialog.accounts.item(i).setCheckState(Qt.CheckState.Checked)
    dialog.description.setPlainText("Mô tả")
    dialog.hashtags.setText("#vlog")
    dialog.accept()
    assert dialog.created == 2

    window = MainWindow(ctx)
    ctx.scheduler.tick = lambda: None  # không đăng thật trong test
    review = _page(window, ReviewPage)
    review.on_show()
    assert review.table.rowCount() == 2

    # Sửa riêng nội dung cho một tài khoản rồi duyệt tất cả
    review.table.selectRow(0)
    review.e_title.setText("Tiêu đề riêng")
    review.table.selectAll()
    review._approve()
    assert review.table.rowCount() == 0

    with ctx.db.session() as s:
        targets = s.query(PostTarget).order_by(PostTarget.id).all()
        assert {t.status for t in targets} == {TargetStatus.SCHEDULED}
        assert "Tiêu đề riêng" in {t.title for t in targets}
        assert {t.account_id for t in targets} >= {acc_a}

    schedule = _page(window, SchedulePage)
    schedule.on_show()
    assert schedule.table.rowCount() == 2
    window.close()


def test_add_account(ctx, monkeypatch):
    from app.ui.pages.accounts import AccountDialog, AccountsPage

    def fake_exec(dialog):
        dialog.name.setText("Kênh mới")
        return AccountDialog.DialogCode.Accepted

    monkeypatch.setattr(AccountDialog, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    window = MainWindow(ctx)
    page = _page(window, AccountsPage)
    page._add()

    with ctx.db.session() as s:
        acc = s.query(Account).one()
        assert acc.platform == Platform.YOUTUBE
        assert acc.profile_dir.endswith(f"youtube-{acc.id}")
    assert page.table.rowCount() == 1
    window.close()


def test_compose_requires_video_and_account(ctx, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    dialog = ComposeDialog(ctx)
    dialog.accept()
    assert "Hãy chọn file video." in warnings[0]
    assert "Hãy chọn ít nhất một tài khoản." in warnings[0]
    assert dialog.created == 0


def test_scheduler_posts_due_target(ctx, video_file):
    """Lịch đăng giao bài đến giờ cho luồng nền và cập nhật kết quả."""
    from app.uploaders import UPLOADERS
    from app.uploaders.base import UploadResult

    acc_id = _add_account(ctx)
    with ctx.db.session() as s:
        from app.core.models import Post, Video

        post = Post(video=Video(file_path=str(video_file)))
        post.targets.append(
            PostTarget(account_id=acc_id, title="T", status=TargetStatus.SCHEDULED, scheduled_at=utcnow() - timedelta(minutes=1))
        )
        s.add(post)
        s.commit()

    calls = []
    uploader = UPLOADERS[Platform.YOUTUBE]
    original = uploader.upload
    uploader.upload = lambda pw, req: calls.append(req) or UploadResult("https://youtu.be/ok")
    # Không khởi động Playwright thật: chạy job ngay trên luồng hiện tại
    ctx.worker.submit = lambda job: ctx.worker.finished.emit(job, job.fn(None), None)
    try:
        ctx.scheduler.tick()
    finally:
        uploader.upload = original

    assert len(calls) == 1
    with ctx.db.session() as s:
        t = s.query(PostTarget).one()
        assert t.status == TargetStatus.SUCCESS
        assert t.result_url == "https://youtu.be/ok"
    assert not ctx.scheduler.is_posting
    assert ctx.scheduler.gap_remaining() is not None  # đang nghỉ giữa hai lần đăng
