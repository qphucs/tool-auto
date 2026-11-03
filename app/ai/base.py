"""Giao diện chung cho mọi nhà cung cấp AI.

Phần còn lại của app chỉ gọi qua AIProvider, nên đổi giữa Ollama, Gemini, Claude
chỉ cần đổi trong Cài đặt. Các provider cụ thể sẽ được viết ở GĐ5.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.core.settings import AISettings


@dataclass(frozen=True)
class ProviderInfo:
    key: str
    label: str
    needs_api_key: bool
    needs_endpoint: bool
    model_hint: str
    note: str


PROVIDERS: dict[str, ProviderInfo] = {
    p.key: p
    for p in (
        ProviderInfo("none", "Chưa dùng AI", False, False, "", "Các tính năng AI sẽ có ở GĐ5."),
        ProviderInfo(
            "ollama",
            "Ollama (chạy trên máy)",
            False,
            True,
            "VD: qwen2.5vl:3b",
            "Miễn phí, chạy offline. GPU 4GB chỉ chạy được model nhỏ (3–4B).",
        ),
        ProviderInfo(
            "gemini",
            "Google Gemini API",
            True,
            False,
            "Sẽ chọn ở GĐ5",
            "Có gói miễn phí và hiểu được video trực tiếp.",
        ),
        ProviderInfo(
            "claude",
            "Claude API (Anthropic)",
            True,
            False,
            "Sẽ chọn ở GĐ5",
            "Viết tiếng Việt tốt nhất, trả phí theo lượng dùng.",
        ),
    )
}


class AIProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str, *, system: str = "") -> str:
        """Sinh văn bản: tiêu đề, mô tả, hashtag, trả lời lệnh chat..."""

    @abstractmethod
    def describe_images(self, prompt: str, image_paths: list[Path]) -> str:
        """Mô tả hoặc phân tích các khung hình trích từ video."""


def create_provider(settings: AISettings, api_key: str = "") -> AIProvider:
    raise NotImplementedError("Tính năng AI sẽ được làm ở GĐ5")
