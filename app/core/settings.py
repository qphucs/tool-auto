import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from app.core import paths

log = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"


@dataclass
class AISettings:
    provider: str = "none"  # none | ollama | gemini | claude
    model: str = ""
    endpoint: str = "http://localhost:11434"
    # API key không lưu ở đây mà lưu trong Windows Credential Manager (xem secrets.py)


@dataclass
class Settings:
    data_dir: str = ""
    min_gap_minutes: int = 10
    max_retries: int = 2
    show_browser: bool = True
    start_with_windows: bool = False
    minimize_to_tray: bool = True
    ai: AISettings = field(default_factory=AISettings)

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_path / "toolauto.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_path / "logs"


def settings_path() -> Path:
    return paths.config_dir() / SETTINGS_FILE


def _pick(cls, data: dict) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def from_dict(data: dict) -> Settings:
    ai = AISettings(**_pick(AISettings, data.get("ai") or {}))
    top = _pick(Settings, data)
    top.pop("ai", None)
    return Settings(**top, ai=ai)


def load_settings() -> Settings:
    data: dict = {}
    path = settings_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("Không đọc được %s, dùng cài đặt mặc định", path)
    settings = from_dict(data)
    if not settings.data_dir:
        settings.data_dir = str(paths.default_data_dir())
    return settings


def save_settings(settings: Settings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
