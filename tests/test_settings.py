import json

from app.core.settings import AISettings, Settings, load_settings, save_settings, settings_path


def test_defaults_when_no_file():
    s = load_settings()
    assert s.data_dir  # luôn có thư mục dữ liệu mặc định
    assert s.ai.text.provider == "none"
    assert s.voice.provider == "edge" and s.voice.voice == "vi-VN-HoaiMyNeural"
    assert s.brand.cta_enabled


def test_roundtrip(tmp_path):
    s = Settings(data_dir=str(tmp_path / "data"))
    s.ai.text.provider, s.ai.text.model = "gemini", "gemini-x"
    s.voice.rate = 10
    s.brand.accent = "#ff0000"
    save_settings(s)

    loaded = load_settings()
    assert loaded.ai.text.provider == "gemini" and loaded.ai.text.model == "gemini-x"
    assert loaded.voice.rate == 10
    assert loaded.brand.accent == "#ff0000"
    assert loaded.projects_dir == tmp_path / "data" / "projects"


def test_ignores_old_unknown_and_wrong_types(tmp_path):
    path = settings_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "data_dir": "X:/d",
        "min_gap_minutes": 3,  # trường của tool cũ
        "ai": {"provider": "claude", "text": {"provider": "groq", "model": 5}},  # model sai kiểu
        "voice": "không phải dict",
    }))
    s = load_settings()
    assert s.data_dir == "X:/d"
    assert s.ai.text.provider == "groq" and s.ai.text.model == ""
    assert s.voice.provider == "edge"

    path.write_text("{not json")
    assert load_settings().ai.text.provider == "none"


def test_api_key_not_in_settings_file(tmp_path):
    save_settings(Settings(data_dir=str(tmp_path)))
    text = settings_path().read_text(encoding="utf-8")
    assert "api_key" not in json.loads(text)["ai"]
    assert "api_key" not in AISettings.__dataclass_fields__
