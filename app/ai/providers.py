"""Các hãng AI cụ thể.

- Claude: dùng SDK chính thức `anthropic`.
- Gemini: REST API của Google.
- Groq, OpenRouter, Ollama: chuẩn API kiểu OpenAI (/chat/completions).
"""

import base64
import logging
import mimetypes
from pathlib import Path

import httpx

from app.ai.base import AIError, AIProvider
from app.core.settings import AISettings, ProviderChoice

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(300.0, connect=15.0)
OLLAMA_TIMEOUT = httpx.Timeout(900.0, connect=10.0)  # model chạy trên máy có thể rất chậm
OPENAI_COMPAT_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"


def _b64(path: Path) -> tuple[str, str]:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return mime, base64.standard_b64encode(path.read_bytes()).decode("ascii")


def _check(resp: httpx.Response, name: str) -> dict:
    if resp.status_code != 200:
        raise AIError(f"{name} báo lỗi {resp.status_code}: {resp.text[:400]}")
    return resp.json()


class ClaudeProvider(AIProvider):
    BETAS = ["server-side-fallback-2026-07-01"]

    def __init__(self, model: str, api_key: str):
        import anthropic  # nhập muộn: chỉ cần khi dùng Claude

        if not api_key:
            raise AIError("Chưa có API key của Claude (trang Cài đặt).")
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3)
        self.model = model or "claude-opus-5-5"

    def complete(self, system: str, prompt: str, images: list[Path] | None = None) -> str:
        content: list[dict] = []
        for img in images or []:
            mime, data = _b64(img)
            content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
        content.append({"type": "text", "text": prompt})
        a = self._anthropic
        try:
            # fallbacks="default": nếu model từ chối vì bộ lọc an toàn, máy chủ tự chạy lại bằng model dự phòng
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_config={"effort": "medium"},
                betas=self.BETAS,
                fallbacks="default",
            )
        except a.AuthenticationError as e:
            raise AIError("API key của Claude không đúng.") from e
        except a.NotFoundError as e:
            raise AIError(f"Không có model Claude tên \"{self.model}\".") from e
        except a.RateLimitError as e:
            raise AIError("Claude đang giới hạn số lần gọi, hãy thử lại sau ít phút.") from e
        except a.BadRequestError as e:
            raise AIError(f"Claude từ chối yêu cầu: {e.message}") from e
        except a.APIStatusError as e:
            raise AIError(f"Claude báo lỗi {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise AIError("Không kết nối được Claude, kiểm tra mạng.") from e
        if response.stop_reason == "refusal":
            raise AIError("Claude từ chối nội dung này.")
        if response.stop_reason == "max_tokens":
            raise AIError("Câu trả lời của Claude bị cắt vì quá dài.")
        return "".join(b.text for b in response.content if b.type == "text")

    def list_models(self) -> list[str]:
        try:
            return [m.id for m in self.client.models.list()]
        except self._anthropic.APIError as e:
            raise AIError(f"Không lấy được danh sách model Claude: {e}") from e


class GeminiProvider(AIProvider):
    def __init__(self, model: str, api_key: str):
        if not api_key:
            raise AIError("Chưa có API key của Gemini (trang Cài đặt).")
        if not model:
            raise AIError("Chưa chọn model Gemini (trang Cài đặt).")
        self.model = model.removeprefix("models/")
        self.headers = {"x-goog-api-key": api_key}

    def complete(self, system: str, prompt: str, images: list[Path] | None = None) -> str:
        parts: list[dict] = []
        for img in images or []:
            mime, data = _b64(img)
            parts.append({"inline_data": {"mime_type": mime, "data": data}})
        parts.append({"text": prompt})
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        try:
            resp = httpx.post(f"{GEMINI_URL}/models/{self.model}:generateContent", headers=self.headers, json=body, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise AIError(f"Không kết nối được Gemini: {e}") from e
        data = _check(resp, "Gemini")
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "không rõ lý do")
            raise AIError(f"Gemini không trả lời ({reason}).")
        return "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))

    def list_models(self) -> list[str]:
        try:
            resp = httpx.get(f"{GEMINI_URL}/models", headers=self.headers, params={"pageSize": 200}, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise AIError(f"Không kết nối được Gemini: {e}") from e
        models = _check(resp, "Gemini").get("models", [])
        return [m["name"].removeprefix("models/") for m in models if "generateContent" in m.get("supportedGenerationMethods", [])]


class OpenAICompatProvider(AIProvider):
    """Groq, OpenRouter, Ollama."""

    def __init__(self, name: str, base_url: str, model: str, api_key: str = "", timeout=TIMEOUT):
        if not model:
            raise AIError(f"Chưa chọn model {name} (trang Cài đặt).")
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.timeout = timeout

    def complete(self, system: str, prompt: str, images: list[Path] | None = None) -> str:
        content: list[dict] = []
        for img in images or []:
            mime, data = _b64(img)
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
        content.append({"type": "text", "text": prompt})
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        try:
            resp = httpx.post(f"{self.base_url}/chat/completions", headers=self.headers, json=body, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise AIError(f"Không kết nối được {self.name}: {e}") from e
        choices = _check(resp, self.name).get("choices") or []
        if not choices:
            raise AIError(f"{self.name} không trả lời.")
        return choices[0].get("message", {}).get("content") or ""

    def list_models(self) -> list[str]:
        try:
            resp = httpx.get(f"{self.base_url}/models", headers=self.headers, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise AIError(f"Không kết nối được {self.name}: {e}") from e
        return sorted(m["id"] for m in _check(resp, self.name).get("data", []))


def create_provider(choice: ProviderChoice, ai: AISettings, api_key: str = "") -> AIProvider:
    p = choice.provider
    if p == "claude":
        return ClaudeProvider(choice.model, api_key)
    if p == "gemini":
        return GeminiProvider(choice.model, api_key)
    if p in OPENAI_COMPAT_URLS:
        if not api_key:
            raise AIError(f"Chưa có API key của {p} (trang Cài đặt).")
        return OpenAICompatProvider(p.capitalize(), OPENAI_COMPAT_URLS[p], choice.model, api_key)
    if p == "ollama":
        return OpenAICompatProvider("Ollama", f"{ai.ollama_url.rstrip('/')}/v1", choice.model, timeout=OLLAMA_TIMEOUT)
    raise AIError("Chưa chọn hãng AI (trang Cài đặt).")
