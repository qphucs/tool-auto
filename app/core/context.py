from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.database import Database
from app.core.settings import Settings

if TYPE_CHECKING:
    from app.ui.tasks import BackgroundTask


@dataclass
class AppContext:
    """Các đối tượng dùng chung, truyền cho mọi trang giao diện."""

    settings: Settings
    db: Database
    media: "BackgroundTask"  # việc nặng chạy nền: chép lời, gọi AI, dựng video
