from datetime import timedelta

from sqlalchemy import text

from app.core.models import Account, Platform, Post, PostTarget, TargetStatus, Video, utcnow
from app.core.stats import dashboard_stats


def _seed(session):
    acc = Account(platform=Platform.YOUTUBE, name="Kênh thử")
    video = Video(file_path="E:/v.mp4", title="Video thử")
    post = Post(video=video)
    now = utcnow()
    statuses = [
        (TargetStatus.PENDING_REVIEW, None),
        (TargetStatus.PENDING_REVIEW, None),
        (TargetStatus.SCHEDULED, None),
        (TargetStatus.FAILED, None),
        (TargetStatus.NEEDS_ATTENTION, None),
        (TargetStatus.SUCCESS, now),
        (TargetStatus.SUCCESS, now - timedelta(days=3)),
    ]
    for status, posted_at in statuses:
        post.targets.append(PostTarget(account=acc, status=status, posted_at=posted_at))
    session.add_all([acc, post])
    session.commit()
    return acc


def test_enums_stored_as_values(db):
    with db.session() as session:
        _seed(session)
        raw = session.execute(text("SELECT platform, status FROM accounts")).one()
    assert raw == ("youtube", "needs_login")


def test_dashboard_stats(db):
    with db.session() as session:
        _seed(session)
        stats = dashboard_stats(session)
    assert stats.accounts == 1
    assert stats.pending_review == 2
    assert stats.scheduled == 1
    assert stats.problems == 2
    assert stats.posted_today == 1


def test_deleting_post_removes_targets(db):
    with db.session() as session:
        _seed(session)
        post = session.query(Post).one()
        session.delete(post)
        session.commit()
        assert session.query(PostTarget).count() == 0
        assert session.query(Account).count() == 1


def test_foreign_keys_enforced(db):
    with db.session() as session:
        assert session.execute(text("PRAGMA foreign_keys")).scalar() == 1
