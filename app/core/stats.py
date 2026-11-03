from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.models import Account, PostTarget, TargetStatus


@dataclass
class DashboardStats:
    accounts: int
    pending_review: int
    scheduled: int
    problems: int
    posted_today: int


def _start_of_today_utc() -> datetime:
    local_midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)


def dashboard_stats(session: Session) -> DashboardStats:
    def count_targets(*statuses: TargetStatus, since: datetime | None = None) -> int:
        q = select(func.count()).select_from(PostTarget).where(PostTarget.status.in_(statuses))
        if since is not None:
            q = q.where(PostTarget.posted_at >= since)
        return session.scalar(q) or 0

    return DashboardStats(
        accounts=session.scalar(select(func.count()).select_from(Account)) or 0,
        pending_review=count_targets(TargetStatus.PENDING_REVIEW),
        scheduled=count_targets(TargetStatus.SCHEDULED),
        problems=count_targets(TargetStatus.FAILED, TargetStatus.NEEDS_ATTENTION),
        posted_today=count_targets(TargetStatus.SUCCESS, since=_start_of_today_utc()),
    )
