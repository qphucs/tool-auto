"""Dùng AI để chia video gốc thành các kiến thức và viết kịch bản video ngắn cho từng kiến thức."""

import logging
import threading
from dataclasses import dataclass

from app.ai.base import AIError, AIProvider, extract_json
from app.editor.ffmpeg import check_cancel
from app.pipeline.script import Script
from app.pipeline.transcribe import Transcript
from app.render.scenes import SCENES, clean_scene, describe_for_prompt

log = logging.getLogger(__name__)

MAX_TOPICS = 12
CHUNK_CHARS = 40_000  # bản chép lời dài hơn sẽ chia đoạn khi tìm kiến thức
WORDS_MIN, WORDS_MAX = 100, 240  # lời đọc cho video 45-90 giây (khoảng 2.6 chữ/giây)
SCENES_MIN, SCENES_MAX = 4, 9


@dataclass
class Topic:
    title: str
    start: float
    end: float
    why: str = ""


SYSTEM = """Bạn là biên tập viên video ngắn (TikTok, Reels, Shorts) chuyên về kiến thức, mẹo công nghệ và AI cho khán giả Việt Nam.
Bạn biến nội dung dài thành video ngắn gọn, dễ hiểu, có nhịp nhanh.
Luôn viết bằng tiếng Việt tự nhiên, có dấu, giọng gần gũi, không sáo rỗng, không thêm thông tin ngoài nội dung được cung cấp.
Chỉ trả lời bằng đúng một khối JSON hợp lệ, không thêm chữ nào khác."""


def _ts(value) -> float:
    """Nhận "mm:ss", "hh:mm:ss" hoặc số giây."""
    if isinstance(value, (int, float)):
        return float(value)
    parts = [float(p) for p in str(value).strip().split(":") if p != ""]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def _chunks(transcript: Transcript) -> list[tuple[float, float]]:
    """Chia bản chép lời dài thành các đoạn (giây bắt đầu, giây kết thúc) khoảng CHUNK_CHARS ký tự."""
    spans, start, size = [], 0.0, 0
    for seg in transcript.segments:
        size += len(seg.text) + 10
        if size > CHUNK_CHARS:
            spans.append((start, seg.end))
            start, size = seg.end, 0
    spans.append((start, transcript.duration))
    return spans


def _topics_prompt(transcript: Transcript, start: float, end: float) -> str:
    return f"""Dưới đây là bản chép lời (có mốc thời gian [phút:giây]) của một video gốc, ngôn ngữ: {transcript.language or "không rõ"}.

Nhiệm vụ: tìm các KIẾN THỨC / MẸO riêng biệt trong video, mỗi cái đủ ý để làm thành MỘT video ngắn 45–90 giây đứng độc lập.
- Chỉ chọn phần có giá trị thật (mẹo, cách làm, khái niệm, lưu ý). Bỏ phần chào hỏi, quảng cáo, lan man.
- Số lượng tùy nội dung, tối đa {MAX_TOPICS}. Video ngắn hoặc ít nội dung thì có thể chỉ 1–2.
- Mỗi kiến thức ứng với một đoạn liên tục trong video gốc, không chồng lên nhau.
- Tiêu đề tiếng Việt, ngắn, hấp dẫn.

Trả về JSON:
{{"topics": [{{"title": "...", "start": "mm:ss", "end": "mm:ss", "why": "vì sao đáng làm video, 1 câu"}}]}}

BẢN CHÉP LỜI:
{transcript.lines(start, end)}"""


def find_topics(ai: AIProvider, transcript: Transcript, cancel: threading.Event | None = None) -> list[Topic]:
    if not transcript.segments:
        raise AIError("Video gốc không có lời nói nào để chép lại.")
    topics: list[Topic] = []
    for start, end in _chunks(transcript):
        check_cancel(cancel)
        data = extract_json(ai.complete(SYSTEM, _topics_prompt(transcript, start, end)))
        for t in data.get("topics", []) if isinstance(data, dict) else []:
            try:
                topic = Topic(str(t["title"]).strip(), _ts(t["start"]), _ts(t["end"]), str(t.get("why", "")).strip())
            except (KeyError, TypeError, ValueError):
                continue
            if topic.title and topic.end > topic.start:
                topics.append(topic)
    topics.sort(key=lambda t: t.start)
    if not topics:
        raise AIError("AI không tìm được kiến thức nào trong video.")
    return topics[:MAX_TOPICS]


def _script_prompt(transcript: Transcript, topic: Topic, cta_by_tool: bool) -> str:
    pad = 5.0
    cta_rule = (
        'KHÔNG viết cảnh "cta" (cảnh kêu gọi cuối video), tool sẽ tự thêm.'
        if cta_by_tool else 'Cảnh cuối là "cta" gợi khán giả bình luận.'
    )
    types = ", ".join(f'"{k}"' for k in SCENES if k != "cta" or not cta_by_tool)
    why = f" ({topic.why})" if topic.why else ""
    return f"""Viết kịch bản MỘT video ngắn dọc 9:16 về kiến thức: "{topic.title}"{why}.
Nội dung lấy từ đoạn {_ts_fmt(topic.start)}–{_ts_fmt(topic.end)} của video gốc (bản chép lời bên dưới). Video gốc có thể là tiếng Anh: hãy viết lại hoàn toàn bằng tiếng Việt.

QUY TẮC
- {SCENES_MIN}–{SCENES_MAX} cảnh. Cảnh 1 là "hook": gây tò mò ngay, nói rõ người xem được gì.
- Tổng lời đọc (narration) {WORDS_MIN}–{WORDS_MAX} chữ. Mỗi cảnh 1–2 câu ngắn, như đang nói chuyện.
- Chữ trên màn hình (data) ngắn hơn lời đọc, chỉ là ý chính. Không lặp nguyên văn lời đọc.
- Dùng đa dạng loại cảnh cho hợp nội dung: các bước dùng "steps", con số dùng "stat", quy trình dùng "diagram",
  lưu ý dùng "warning", gần cuối nên có "summary". {cta_rule}
- "line2" là phần quan trọng nhất của tiêu đề, sẽ được nhấn màu. Icon là 1 emoji phù hợp.
- Chỉ dùng thông tin có trong bản chép lời. Không bịa số liệu.
- Hình minh họa ("visual") cho mỗi cảnh:
  - {{"kind": "source", "time": "mm:ss"}}: lấy khung hình video gốc tại thời điểm đó, CHỈ khi lúc đó màn hình gốc
    nhiều khả năng đang hiện thứ đáng xem (giao diện phần mềm, trang web, slide, sơ đồ). Dùng với cảnh "screenshot".
  - {{"kind": "web", "url": "https://..."}}: chụp trang web công khai được nhắc tới rõ ràng. Dùng với cảnh "screenshot".
  - {{"kind": "none"}}: các trường hợp khác (mặc định).

CÁC LOẠI CẢNH ({types}) VÀ TRƯỜNG DỮ LIỆU
{describe_for_prompt()}

Trả về JSON:
{{"title": "tiêu đề video", "summary": "1 câu tóm tắt",
  "scenes": [{{"type": "hook", "narration": "lời đọc", "data": {{...}}, "visual": {{"kind": "none"}}}}]}}

BẢN CHÉP LỜI:
{transcript.lines(max(0.0, topic.start - pad), topic.end + pad)}"""


def _ts_fmt(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def _to_script(data, topic: Topic) -> Script:
    if not isinstance(data, dict):
        raise AIError("AI trả về kịch bản sai định dạng.")
    for s in data.get("scenes") or []:
        if isinstance(s, dict) and isinstance(s.get("visual"), dict) and "time" in s["visual"]:
            try:
                s["visual"]["time"] = _ts(s["visual"]["time"])
            except (TypeError, ValueError):
                s["visual"]["time"] = None
    script = Script.from_dict(data)
    script.start, script.end = topic.start, topic.end
    for s in script.scenes:
        s.data, _ = clean_scene(s.type, s.data)  # cắt chữ quá dài, bỏ trường lạ
    return script


def _review(script: Script) -> list[str]:
    """Các vấn đề nghiêm trọng cần AI sửa lại."""
    issues = []
    if not SCENES_MIN <= len(script.scenes) <= SCENES_MAX + 1:
        issues.append(f"Cần {SCENES_MIN}–{SCENES_MAX} cảnh, đang có {len(script.scenes)}.")
    words = script.narration_words()
    if not WORDS_MIN * 0.8 <= words <= WORDS_MAX * 1.2:
        issues.append(f"Tổng lời đọc cần {WORDS_MIN}–{WORDS_MAX} chữ, đang có {words}.")
    if script.scenes and script.scenes[0].type != "hook":
        issues.append('Cảnh đầu tiên phải là "hook".')
    issues += [p for p in script.problems() if "còn trống" in p or "cần" in p]
    return issues


def write_script(ai: AIProvider, transcript: Transcript, topic: Topic, cta_by_tool: bool = True,
                 cancel: threading.Event | None = None) -> Script:
    prompt = _script_prompt(transcript, topic, cta_by_tool)
    check_cancel(cancel)
    reply = ai.complete(SYSTEM, prompt)
    script = _to_script(extract_json(reply), topic)
    issues = _review(script)
    if issues:
        log.info("Kịch bản \"%s\" cần sửa: %s", topic.title, issues)
        check_cancel(cancel)
        fix = (f"{prompt}\n\nBẢN NHÁP TRƯỚC CỦA BẠN:\n{reply}\n\nBản nháp có các vấn đề sau, hãy sửa và trả lại "
               "TOÀN BỘ kịch bản JSON:\n- " + "\n- ".join(issues))
        try:
            script = _to_script(extract_json(ai.complete(SYSTEM, fix)), topic)
        except AIError:
            log.warning("AI sửa kịch bản thất bại, giữ bản nháp đầu")
    if cta_by_tool:
        script.scenes = [s for s in script.scenes if s.type != "cta"]
    if not script.title.strip() or script.title == "Video chưa đặt tên":
        script.title = topic.title
    return script
