"""Quy tắc chuyển trạng thái bài đăng: duyệt, lên lịch, đăng, thử lại."""

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import PLATFORM_LABELS, AccountStatus, PostTarget, TargetStatus
from app.core.settings import Settings
from app.uploaders import get_uploader
from app.uploaders.base import LoginRequired, NeedsAttention, UploadRequest, parse_hashtags

RETRY_DELAY = timedelta(minutes=5)
# Quá giờ đăng hơn mức này lúc mở app thì hỏi bạn có đăng bù không
OVERDUE_GRACE = timedelta(minutes=15)
INTERRUPTED_MESSAGE = (
    "App bị tắt khi đang đăng. Kiểm tra trên nền tảng xem video đã lên chưa, nếu chưa thì bấm Thử lại."
)


def validate_target(t: PostTarget) -> list[str]:
    uploader = get_uploader(t.account.platform)
    if uploader is None:
        return [f"Chưa hỗ trợ đăng lên {PLATFORM_LABELS[t.account.platform]}."]
    problems = []
    if not Path(t.post.video.file_path).is_file():
        problems.append(f"Không tìm thấy file video: {t.post.video.file_path}")
    problems += uploader.validate(t.title, t.description, parse_hashtags(t.hashtags))
    return problems


def approve(t: PostTarget, now: datetime) -> list[str]:
    problems = validate_target(t)
    if problems:
        return problems
    t.status = TargetStatus.SCHEDULED
    if t.scheduled_at is None or t.scheduled_at < now:
        t.scheduled_at = now
    return []


def unschedule(t: PostTarget) -> None:
    t.status = TargetStatus.PENDING_REVIEW


def retry(t: PostTarget, now: datetime) -> None:
    t.status = TargetStatus.SCHEDULED
    t.scheduled_at = now
    t.attempts = 0
    t.last_error = ""


def next_due(session: Session, now: datetime, skip_accounts: set[int] = frozenset()) -> PostTarget | None:
    q = (
        select(PostTarget)
        .where(PostTarget.status == TargetStatus.SCHEDULED, PostTarget.scheduled_at <= now)
        .order_by(PostTarget.scheduled_at, PostTarget.id)
    )
    return next((t for t in session.scalars(q) if t.account_id not in skip_accounts), None)


def start_posting(t: PostTarget) -> None:
    t.status = TargetStatus.POSTING
    t.attempts += 1
    t.last_error = ""


def build_request(t: PostTarget, settings: Settings) -> UploadRequest:
    return UploadRequest(
        video_path=Path(t.post.video.file_path),
        title=t.title,
        description=t.description,
        hashtags=parse_hashtags(t.hashtags),
        visibility=t.visibility,
        profile_dir=Path(t.account.profile_dir),
        screenshot_dir=settings.data_path / "screenshots",
        headless=not settings.show_browser,
    )


def finish_success(t: PostTarget, url: str, now: datetime) -> None:
    t.status = TargetStatus.SUCCESS
    t.posted_at = now
    t.result_url = url
    t.last_error = ""
    t.account.status = AccountStatus.ACTIVE


def finish_error(t: PostTarget, error: Exception, now: datetime, max_retries: int) -> None:
    t.last_error = str(error) or error.__class__.__name__
    if isinstance(error, LoginRequired):
        t.account.status = AccountStatus.EXPIRED
    if isinstance(error, NeedsAttention):
        t.status = TargetStatus.NEEDS_ATTENTION
    elif t.attempts <= max_retries:
        t.status = TargetStatus.SCHEDULED
        t.scheduled_at = now + RETRY_DELAY
    else:
        t.status = TargetStatus.FAILED


def recover_interrupted(session: Session) -> int:
    targets = session.scalars(select(PostTarget).where(PostTarget.status == TargetStatus.POSTING)).all()
    for t in targets:
        t.status = TargetStatus.NEEDS_ATTENTION
        t.last_error = INTERRUPTED_MESSAGE
    return len(targets)


def overdue(session: Session, now: datetime) -> list[PostTarget]:
    q = select(PostTarget).where(
        PostTarget.status == TargetStatus.SCHEDULED, PostTarget.scheduled_at < now - OVERDUE_GRACE
    )
    return list(session.scalars(q))
