import dataclasses
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.core import paths

log = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"


@dataclass
class ProviderChoice:
    provider: str = "none"  # none | gemini | claude | groq | openrouter | ollama
    model: str = ""


@dataclass
class AISettings:
    text: ProviderChoice = field(default_factory=ProviderChoice)  # chia kiến thức, viết kịch bản
    vision: ProviderChoice = field(default_factory=ProviderChoice)  # chọn khung hình
    ollama_url: str = "http://localhost:11434"
    # API key không lưu ở đây mà lưu trong Windows Credential Manager (xem secrets.py)


@dataclass
class VoiceSettings:
    provider: str = "edge"  # edge | google | windows
    voice: str = "vi-VN-HoaiMyNeural"
    rate: int = 0  # phần trăm nhanh/chậm so với bình thường, -50..50


@dataclass
class WhisperSettings:
    model: str = "small"  # tiny | base | small | medium
    device: str = "cpu"  # cpu | cuda


@dataclass
class BrandSettings:
    bg1: str = "#070b18"
    bg2: str = "#101a36"
    text: str = "#f4f6fb"
    muted: str = "#9aa5bd"
    accent: str = "#4f8cff"
    accent2: str = "#ffa64d"
    accent3: str = "#ff5d6c"
    accent4: str = "#3ddc97"
    font: str = "Segoe UI"
    channel: str = ""
    logo: str = ""
    show_logo: bool = False
    cta_enabled: bool = True
    cta_question: str = "Bạn muốn xem mẹo nào tiếp theo?"
    cta_hint: str = "Bình luận cho mình biết nhé"
    cta_button: str = "Đăng ký kênh"


@dataclass
class Settings:
    data_dir: str = ""
    ai: AISettings = field(default_factory=AISettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    whisper: WhisperSettings = field(default_factory=WhisperSettings)
    brand: BrandSettings = field(default_factory=BrandSettings)

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_path / "toolauto.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_path / "logs"

    @property
    def projects_dir(self) -> Path:
        return self.data_path / "projects"

    @property
    def outputs_dir(self) -> Path:
        return self.data_path / "outputs"

    @property
    def models_dir(self) -> Path:
        return self.data_path / "models"


def settings_path() -> Path:
    return paths.config_dir() / SETTINGS_FILE


def _build(cls, data):
    """Tạo dataclass từ dict, bỏ qua trường lạ và trường sai kiểu (giữ giá trị mặc định)."""
    obj = cls()
    if not isinstance(data, dict):
        return obj
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        current = getattr(obj, f.name)
        value = data[f.name]
        if dataclasses.is_dataclass(current):
            setattr(obj, f.name, _build(type(current), value))
        elif type(value) is type(current):
            setattr(obj, f.name, value)
    return obj


def from_dict(data: dict) -> Settings:
    return _build(Settings, data)


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
