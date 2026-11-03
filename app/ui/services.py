from app.core.context import AppContext
from app.core.database import Database
from app.core.settings import Settings
from app.ui.tasks import BackgroundTask


def create_context(settings: Settings, db: Database) -> AppContext:
    return AppContext(settings=settings, db=db, media=BackgroundTask())
