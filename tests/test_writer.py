import copy

import pytest

from app.ai.base import AIError
from app.pipeline.transcribe import Segment, Transcript
from app.pipeline.writer import Topic, find_topics, write_script
from tests.fakes import FakeAI, good_script


@pytest.fixture
def transcript():
    return Transcript("en", 300.0, [Segment(i * 10.0, i * 10.0 + 9, f"Câu số {i} nói về mẹo dùng AI.") for i in range(30)])


def test_find_topics_parses_times(transcript):
    ai = FakeAI([{"topics": [
        {"title": "Mẹo B", "start": "02:00", "end": "03:00", "why": "hay"},
        {"title": "Mẹo A", "start": 10, "end": "01:05"},
        {"title": "", "start": 0, "end": 1},  # thiếu tiêu đề: bỏ
        {"title": "Sai giờ", "start": "05:00", "end": "04:00"},  # kết thúc trước bắt đầu: bỏ
    ]}])
    topics = find_topics(ai, transcript)
    assert [t.title for t in topics] == ["Mẹo A", "Mẹo B"]
    assert (topics[0].start, topics[0].end) == (10.0, 65.0)
    assert "[00:10] Câu số 1" in ai.prompts[0][0]


def test_find_topics_errors(transcript):
    with pytest.raises(AIError):
        find_topics(FakeAI([{"topics": []}]), transcript)
    with pytest.raises(AIError):
        find_topics(FakeAI([]), Transcript("vi", 10.0, []))


def test_write_script_cleans_and_drops_cta(transcript):
    ai = FakeAI([good_script()])
    script = write_script(ai, transcript, Topic("Mẹo thử", 60, 120))
    assert [s.type for s in script.scenes][0] == "hook"
    assert "cta" not in [s.type for s in script.scenes]  # tool tự thêm cảnh kêu gọi
    assert script.scenes[2].visual.time == 3.0  # "00:03" -> giây
    assert (script.start, script.end) == (60, 120)
    prompt = ai.prompts[0][0]
    # Chỉ gửi các câu chạm vào đoạn 55s–125s (±5 giây quanh kiến thức)
    assert "[00:50]" in prompt and "[02:00]" in prompt
    assert "[00:40]" not in prompt and "[02:10]" not in prompt
    assert "()" not in prompt.splitlines()[0]
    assert 'KHÔNG viết cảnh "cta"' in prompt


def test_write_script_asks_ai_to_fix(transcript):
    bad = copy.deepcopy(good_script())
    bad["scenes"] = bad["scenes"][:2]  # quá ít cảnh
    ai = FakeAI([bad, good_script(title="Đã sửa")])
    script = write_script(ai, transcript, Topic("Mẹo", 0, 60))
    assert script.title == "Đã sửa"
    assert len(ai.prompts) == 2 and "Cần 4–9 cảnh" in ai.prompts[1][0]


def test_write_script_keeps_draft_if_fix_fails(transcript):
    bad = copy.deepcopy(good_script(title="Bản đầu"))
    bad["scenes"] = bad["scenes"][:3]
    script = write_script(FakeAI([bad, "không phải json"]), transcript, Topic("Mẹo", 0, 60))
    assert script.title == "Bản đầu"
