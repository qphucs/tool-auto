from datetime import timedelta

from app.core import posting
from app.core.models import (
    Account,
    AccountStatus,
    Platform,
    Post,
    PostTarget,
    TargetStatus,
    Video,
    utcnow,
)
from app.core.settings import Settings
from app.uploaders.base import LoginRequired, NeedsAttention, UploadError, parse_hashtags


def _target(session, video_file, **kw) -> PostTarget:
    acc = Account(platform=Platform.YOUTUBE, name="Kênh", profile_dir="E:/p/youtube-1")
    post = Post(video=Video(file_path=str(video_file)))
    defaults = dict(title="Tiêu đề", description="Mô tả", status=TargetStatus.PENDING_REVIEW)
    t = PostTarget(account=acc, **(defaults | kw))
    post.targets.append(t)
    session.add(post)
    session.commit()
    return t


def test_parse_hashtags():
    assert parse_hashtags("#a b,  #a ##c") == ["#a", "#b", "#c"]
    assert parse_hashtags("") == []


def test_approve_sets_time_and_validates(db, video_file):
    now = utcnow()
    with db.session() as s:
        t = _target(s, video_file, scheduled_at=now - timedelta(hours=1))
        assert posting.approve(t, now) == []
        assert t.status == TargetStatus.SCHEDULED
        assert t.scheduled_at == now  # giờ đã qua thì đăng ngay

        bad = _target(s, video_file, title="x" * 101 + "<")
        problems = posting.approve(bad, now)
        assert len(problems) == 2
        assert bad.status == TargetStatus.PENDING_REVIEW


def test_approve_rejects_missing_file(db, tmp_path):
    with db.session() as s:
        t = _target(s, tmp_path / "missing.mp4")
        assert "Không tìm thấy file video" in posting.approve(t, utcnow())[0]


def test_next_due_order_and_skip(db, video_file):
    now = utcnow()
    with db.session() as s:
        later = _target(s, video_file, status=TargetStatus.SCHEDULED, scheduled_at=now - timedelta(minutes=1))
        first = _target(s, video_file, status=TargetStatus.SCHEDULED, scheduled_at=now - timedelta(minutes=5))
        _target(s, video_file, status=TargetStatus.SCHEDULED, scheduled_at=now + timedelta(minutes=5))
        assert posting.next_due(s, now).id == first.id
        assert posting.next_due(s, now, {first.account_id}).id == later.id


def test_retry_then_fail(db, video_file):
    now = utcnow()
    with db.session() as s:
        t = _target(s, video_file, status=TargetStatus.SCHEDULED, scheduled_at=now)
        for attempt in (1, 2):
            posting.start_posting(t)
            posting.finish_error(t, UploadError("mạng lỗi"), now, max_retries=2)
            assert t.status == TargetStatus.SCHEDULED, attempt
            assert t.scheduled_at == now + posting.RETRY_DELAY
        posting.start_posting(t)
        posting.finish_error(t, UploadError("mạng lỗi"), now, max_retries=2)
        assert t.status == TargetStatus.FAILED
        assert t.attempts == 3

        posting.retry(t, now)
        assert (t.status, t.attempts, t.last_error) == (TargetStatus.SCHEDULED, 0, "")


def test_needs_attention_is_not_retried(db, video_file):
    now = utcnow()
    with db.session() as s:
        t = _target(s, video_file, status=TargetStatus.SCHEDULED, scheduled_at=now)
        posting.start_posting(t)
        posting.finish_error(t, NeedsAttention("captcha"), now, max_retries=5)
        assert t.status == TargetStatus.NEEDS_ATTENTION

        t2 = _target(s, video_file, status=TargetStatus.SCHEDULED, scheduled_at=now)
        posting.start_posting(t2)
        posting.finish_error(t2, LoginRequired("hết phiên"), now, max_retries=5)
        assert t2.status == TargetStatus.NEEDS_ATTENTION
        assert t2.account.status == AccountStatus.EXPIRED


def test_success(db, video_file):
    now = utcnow()
    with db.session() as s:
        t = _target(s, video_file, status=TargetStatus.POSTING)
        posting.finish_success(t, "https://youtu.be/x", now)
        assert (t.status, t.posted_at, t.result_url) == (TargetStatus.SUCCESS, now, "https://youtu.be/x")
        assert t.account.status == AccountStatus.ACTIVE


def test_recover_and_overdue(db, video_file):
    now = utcnow()
    with db.session() as s:
        stuck = _target(s, video_file, status=TargetStatus.POSTING)
        old = _target(s, video_file, status=TargetStatus.SCHEDULED, scheduled_at=now - timedelta(hours=2))
        _target(s, video_file, status=TargetStatus.SCHEDULED, scheduled_at=now - timedelta(minutes=5))
        assert posting.recover_interrupted(s) == 1
        assert stuck.status == TargetStatus.NEEDS_ATTENTION
        assert [t.id for t in posting.overdue(s, now)] == [old.id]


def test_build_request(db, video_file, tmp_path):
    settings = Settings(data_dir=str(tmp_path / "data"), show_browser=False)
    with db.session() as s:
        t = _target(s, video_file, hashtags="#a b", visibility="unlisted")
        req = posting.build_request(t, settings)
    assert req.hashtags == ["#a", "#b"]
    assert req.visibility == "unlisted"
    assert req.headless is True
    assert req.screenshot_dir == tmp_path / "data" / "screenshots"
