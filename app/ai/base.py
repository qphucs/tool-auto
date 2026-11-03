"""Giao diện chung cho mọi hãng AI.

Phần còn lại của app chỉ gọi AIProvider.complete(), nên đổi hãng chỉ cần đổi trong Cài đặt.
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


class AIError(Exception):
    pass


@dataclass(frozen=True)
class ProviderInfo:
    key: str
    label: str
    needs_api_key: bool
    model_hint: str
    note: str
    vision: bool = True  # hãng có model đọc được ảnh


PROVIDERS: dict[str, ProviderInfo] = {
    p.key: p
    for p in (
        ProviderInfo("none", "Không dùng", False, "", "Tắt việc này.", vision=False),
        ProviderInfo("gemini", "Google Gemini", True, "VD: gemini-2.5-flash",
                     "Có gói miễn phí, đọc ảnh tốt. Lấy key tại aistudio.google.com."),
        ProviderInfo("claude", "Claude (Anthropic)", True, "claude-opus-5-5",
                     "Viết tiếng Việt tốt nhất, trả phí theo lượng dùng. Lấy key tại platform.claude.com."),
        ProviderInfo("groq", "Groq", True, "VD: qwen/qwen3.8-27b",
                     "Rất nhanh, có gói miễn phí. Lấy key tại console.groq.com."),
        ProviderInfo("openrouter", "OpenRouter", True, "VD: tên model có đuôi :free",
                     "Một key dùng được nhiều hãng, có model miễn phí. Lấy key tại openrouter.ai."),
        ProviderInfo("ollama", "Ollama (chạy trên máy)", False, "VD: qwen2.5vl:3b",
                     "Miễn phí, offline. GPU 4GB chỉ chạy được model nhỏ, kịch bản tiếng Việt sẽ yếu."),
    )
}


class AIProvider(ABC):
    @abstractmethod
    def complete(self, system: str, prompt: str, images: list[Path] | None = None) -> str:
        """Gửi câu lệnh (kèm ảnh nếu có), trả về chữ AI trả lời."""

    @abstractmethod
    def list_models(self) -> list[str]:
        """Các model mà key này dùng được (để chọn trong Cài đặt)."""


def extract_json(text: str):
    """Lấy JSON từ câu trả lời của AI (bỏ khung ```json, chữ thừa trước/sau)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if starts:
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        if end > start:
            try:
                return json.loads(text[start : end + 1])
            except ValueError:
                pass
    raise AIError("AI không trả về JSON hợp lệ.")
