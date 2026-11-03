"""Đồ giả dùng chung cho test: AI trả lời sẵn, giọng đọc tạo bằng FFmpeg."""

import json
import subprocess
from pathlib import Path

from app.ai.base import AIProvider
from app.pipeline.tts import Speech


def good_script(title="Mẹo thử", time="00:03") -> dict:
    return {
        "title": title, "summary": "tóm tắt",
        "scenes": [
            {"type": "hook", "narration": "Một mẹo nhỏ giúp bạn làm việc nhanh hơn mỗi ngày với AI " * 3,
             "data": {"line1": "Mẹo nhỏ", "line2": "nhanh gấp đôi", "chips": [{"icon": "⚡", "text": "Nhanh"}]}},
            {"type": "question", "narration": "Bạn có bao giờ mất cả giờ chỉ để viết một email đơn giản không " * 2,
             "data": {"line1": "Mất cả giờ", "line2": "cho một email?"}},
            {"type": "screenshot", "narration": "Đây là màn hình làm việc, bạn chỉ cần gõ một câu ngắn gọn " * 2,
             "data": {"line1": "Gõ một câu", "line2": "là xong"}, "visual": {"kind": "source", "time": time}},
            {"type": "steps", "narration": "Hãy làm theo ba bước sau để có kết quả tốt nhất ngay lần đầu tiên " * 2,
             "data": {"line1": "Ba bước", "items": [{"icon": "1️⃣", "text": "Nêu mục tiêu"}, {"icon": "2️⃣", "text": "Cho ví dụ"}]}},
            {"type": "summary", "narration": "Lưu lại những ý này để áp dụng ngay hôm nay nhé các bạn " * 2,
             "data": {"line1": "Lưu lại", "items": ["Nêu mục tiêu", "Cho ví dụ"]}},
            {"type": "cta", "narration": "Bình luận nhé", "data": {"question": "Bạn thích mẹo nào?"}},
        ],
    }


class FakeAI(AIProvider):
    """Trả lời theo thứ tự trong `replies` (chuỗi hoặc dict), ghi lại các câu lệnh đã nhận."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[tuple[str, list]] = []

    def complete(self, system, prompt, images=None):
        self.prompts.append((prompt, list(images or [])))
        reply = self.replies.pop(0)
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)

    def list_models(self):
        return ["fake"]


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def make_video(path: Path, seconds: int = 12) -> Path:
    ffmpeg("-f", "lavfi", "-i", f"testsrc=size=640x360:rate=25:duration={seconds}",
           "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}", "-shortest", "-pix_fmt", "yuv420p", str(path))
    return path


def fake_synthesize(text, out_dir, voice, api_key="", cancel=None) -> Speech:
    """Thay giọng đọc thật: một đoạn tiếng bíp dài theo số chữ."""
    out_dir.mkdir(parents=True, exist_ok=True)
    words = text.split()
    duration = round(max(1.0, len(words) * 0.3), 2)
    audio = out_dir / f"fake-{abs(hash(text))}.mp3"
    if not audio.exists():
        ffmpeg("-f", "lavfi", "-i", f"sine=frequency=500:duration={duration}", str(audio))
    step = duration / len(words)
    return Speech(audio, duration, [{"w": w, "start": i * step, "end": (i + 1) * step} for i, w in enumerate(words)])
