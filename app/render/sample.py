"""Một kịch bản mẫu viết tay có đủ các loại cảnh, dùng để xem thử giao diện và để test."""

from app.pipeline.script import Scene, Script

SAMPLE_SCENES = [
    ("hook", {
        "tag": "Mẹo AI", "line1": "Học bất cứ thứ gì", "line2": "nhanh gấp 3 lần",
        "chips": [{"icon": "🎯", "text": "Hỏi đúng"}, {"icon": "🧠", "text": "Ôn đúng lúc"},
                  {"icon": "🗂️", "text": "Tóm tắt"}, {"icon": "🧪", "text": "Tự kiểm tra"}],
    }, "Ba mẹo dùng AI để học bất cứ thứ gì nhanh gấp ba lần."),
    ("question", {
        "icon": "🤔", "line1": "Vì sao đọc mãi", "line2": "vẫn không nhớ?", "accent": "accent-2",
        "sub": "Đọc lại nhiều lần tạo cảm giác hiểu, nhưng não chưa thật sự ghi nhớ.",
    }, "Vì sao đọc đi đọc lại mà vẫn không nhớ được?"),
    ("stat", {
        "tag": "Nghiên cứu", "value": 50, "suffix": "%", "label": "kiến thức quên sau 1 ngày",
        "note": "Nếu không ôn lại đúng lúc", "accent": "accent-3",
    }, "Chúng ta quên khoảng một nửa kiến thức chỉ sau một ngày."),
    ("steps", {
        "tag": "01 — Áp dụng", "line1": "Hỏi AI", "line2": "theo 3 bước",
        "items": [{"icon": "✍️", "text": "Giải thích như cho học sinh lớp 5"},
                  {"icon": "🔎", "text": "Cho 3 ví dụ đời thường"},
                  {"icon": "❓", "text": "Đặt 5 câu hỏi kiểm tra"}],
    }, "Hãy nhờ AI giải thích thật đơn giản, cho ví dụ đời thường, rồi đặt câu hỏi kiểm tra bạn."),
    ("screenshot", {
        "line1": "Gõ một câu", "line2": "là có bài kiểm tra", "accent": "accent-4",
        "url": "chat.example.com", "caption": "Câu lệnh mẫu", "caption_icon": "💬",
    }, "Chỉ cần gõ một câu là AI tạo ngay bài kiểm tra cho bạn."),
    ("diagram", {
        "line1": "Vòng lặp", "line2": "học hiệu quả",
        "nodes": [{"icon": "📖", "text": "Học ý mới"}, {"icon": "❓", "text": "AI hỏi lại"},
                  {"icon": "🔁", "text": "Ôn phần sai"}],
    }, "Học ý mới, để AI hỏi lại, rồi ôn đúng phần bạn trả lời sai."),
    ("warning", {
        "level": "warning", "title": "Đừng tin 100%",
        "text": "AI có thể bịa thông tin. Luôn kiểm tra lại với nguồn chính thống.",
        "bullets": ["Hỏi AI dẫn nguồn", "Đối chiếu sách hoặc tài liệu gốc"],
    }, "Nhưng đừng tin AI hoàn toàn, hãy luôn kiểm tra lại nguồn."),
    ("summary", {
        "line1": "Lưu lại", "line2": "để dùng ngay",
        "items": ["Hỏi đơn giản, có ví dụ", "Để AI kiểm tra bạn", "Ôn đúng phần sai", "Luôn kiểm tra nguồn"],
    }, "Lưu lại bốn ý này để áp dụng ngay hôm nay."),
]


def sample_script() -> Script:
    return Script(
        title="3 mẹo dùng AI để học nhanh",
        scenes=[Scene(t, narration, data) for t, data, narration in SAMPLE_SCENES],
    )
