import json

from app.core import settings as settings_mod
from app.core.settings import Settings, load_settings, save_settings, settings_path


def test_defaults_when_no_file():
    s = load_settings()
    assert s.data_dir  # luôn có thư mục dữ liệu mặc định
    assert s.min_gap_minutes == 10
    assert s.ai.provider == "none"


def test_roundtrip(tmp_path):
    s = Settings(data_dir=str(tmp_path / "data"), min_gap_minutes=25)
    s.ai.provider = "ollama"
    s.ai.model = "qwen2.5vl:3b"
    save_settings(s)

    loaded = load_settings()
    assert loaded.data_dir == str(tmp_path / "data")
    assert loaded.min_gap_minutes == 25
    assert loaded.ai.provider == "ollama"
    assert loaded.ai.model == "qwen2.5vl:3b"


def test_ignores_unknown_and_corrupt_fields(tmp_path):
    path = settings_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"min_gap_minutes": 3, "old_field": 1, "ai": {"provider": "claude", "x": 2}}))
    s = load_settings()
    assert s.min_gap_minutes == 3
    assert s.ai.provider == "claude"

    path.write_text("{not json")
    assert load_settings().min_gap_minutes == Settings().min_gap_minutes


def test_api_key_not_in_settings_file(tmp_path):
    save_settings(Settings(data_dir=str(tmp_path)))
    saved = json.loads(settings_path().read_text(encoding="utf-8"))
    assert "api_key" not in saved["ai"]
    assert "api_key" not in settings_mod.AISettings.__dataclass_fields__
