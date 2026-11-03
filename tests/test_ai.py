from types import SimpleNamespace

import httpx
import pytest

from app.ai import providers
from app.ai.base import AIError, extract_json
from app.ai.providers import ClaudeProvider, OpenAICompatProvider, create_provider
from app.core.settings import AISettings, ProviderChoice


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Đây là kết quả:\n```json\n{"a": [1, 2]}\n```\nXong.') == {"a": [1, 2]}
    assert extract_json('Chắc chắn rồi! {"a": "b"} Chúc vui') == {"a": "b"}
    with pytest.raises(AIError):
        extract_json("không có json")


def test_create_provider_requires_settings():
    ai = AISettings()
    with pytest.raises(AIError, match="Chưa chọn"):
        create_provider(ProviderChoice("none"), ai)
    for p in ("gemini", "groq", "openrouter", "claude"):
        with pytest.raises(AIError, match="API key"):
            create_provider(ProviderChoice(p, "m"), ai, "")
    ollama = create_provider(ProviderChoice("ollama", "qwen"), AISettings(ollama_url="http://localhost:9999/"), "")
    assert ollama.base_url == "http://localhost:9999/v1"


def test_openai_compat_sends_images(monkeypatch, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG fake")
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, headers=headers, body=json)
        return httpx.Response(200, json={"choices": [{"message": {"content": "xin chào"}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    p = OpenAICompatProvider("Groq", "https://api.groq.com/openai/v1", "m", "KEY")
    assert p.complete("hệ thống", "câu hỏi", [img]) == "xin chào"
    assert sent["url"].endswith("/chat/completions")
    assert sent["headers"]["Authorization"] == "Bearer KEY"
    content = sent["body"]["messages"][1]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1] == {"type": "text", "text": "câu hỏi"}

    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: httpx.Response(401, text="bad key"))
    with pytest.raises(AIError, match="401"):
        p.complete("s", "q")


def test_claude_uses_sdk_with_fallbacks(monkeypatch):
    p = ClaudeProvider("", "KEY")
    assert p.model == "claude-opus-5-5"
    calls = {}

    def fake_create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[
            SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text='{"ok": true}'),
        ])

    monkeypatch.setattr(p.client.beta.messages, "create", fake_create)
    assert p.complete("hệ thống", "câu hỏi") == '{"ok": true}'
    assert calls["fallbacks"] == "default"
    assert calls["betas"] == ["server-side-fallback-2026-07-01"]
    assert calls["system"] == "hệ thống"

    monkeypatch.setattr(p.client.beta.messages, "create",
                        lambda **k: SimpleNamespace(stop_reason="refusal", content=[]))
    with pytest.raises(AIError, match="từ chối"):
        p.complete("s", "q")
