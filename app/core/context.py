from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.database import Database
from app.core.settings import Settings

if TYPE_CHECKING:
    from app.automation.login_windows import LoginWindows
    from app.automation.worker import AutomationWorker
    from app.ui.scheduler import PostScheduler
    from app.ui.tasks import BackgroundTask


@dataclass
class AppContext:
    """Các đối tượng dùng chung, truyền cho mọi trang giao diện."""

    settings: Settings
    db: Database
    worker: "AutomationWorker"
    logins: "LoginWindows"
    scheduler: "PostScheduler"
    media: "BackgroundTask"  # phân tích / dựng video
