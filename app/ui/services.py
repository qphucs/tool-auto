from app.automation.login_windows import LoginWindows
from app.automation.worker import AutomationWorker
from app.core.context import AppContext
from app.core.database import Database
from app.core.settings import Settings
from app.ui.scheduler import PostScheduler
from app.ui.tasks import BackgroundTask


def create_context(settings: Settings, db: Database) -> AppContext:
    worker = AutomationWorker()
    logins = LoginWindows()
    scheduler = PostScheduler(settings, db, worker, logins)
    return AppContext(
        settings=settings, db=db, worker=worker, logins=logins, scheduler=scheduler, media=BackgroundTask()
    )
