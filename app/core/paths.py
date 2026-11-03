import os
from pathlib import Path

APP_DIR_NAME = "ToolAuto"
DATA_DIR_NAME = "ToolAuto-data"
DATA_SUBDIRS = ("projects", "outputs", "models", "logs")


def config_dir() -> Path:
    """Thư mục chứa settings.json (nhỏ, luôn nằm trong AppData)."""
    override = os.environ.get("TOOLAUTO_CONFIG_DIR")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_DIR_NAME


def default_data_dir() -> Path:
    # Ổ C và D gần đầy nên ưu tiên ổ E nếu có
    if Path("E:/").exists():
        return Path("E:/") / DATA_DIR_NAME
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / APP_DIR_NAME / "data"


def ensure_data_dirs(data_dir: Path) -> None:
    for name in DATA_SUBDIRS:
        (data_dir / name).mkdir(parents=True, exist_ok=True)
