"""Khuôn dữ liệu của từng loại cảnh.

Dùng để: làm gọn nội dung AI viết (bỏ trường lạ, cắt chữ quá dài), báo vấn đề cho bạn khi duyệt,
và mô tả khuôn cho AI trong câu lệnh viết kịch bản.
"""

from dataclasses import dataclass, field

ACCENTS = ("accent", "accent-2", "accent-3", "accent-4")
LEVELS = ("tip", "warning", "danger")


@dataclass(frozen=True)
class Text:
    max_len: int
    required: bool = False
    hint: str = ""


@dataclass(frozen=True)
class Choice:
    values: tuple[str, ...]
    default: str


@dataclass(frozen=True)
class Number:
    required: bool = False
    integer: bool = False


@dataclass(frozen=True)
class Items:
    """Danh sách mục {icon, text} hoặc danh sách chữ (plain=True)."""

    max_items: int
    text_len: int
    min_items: int = 0
    plain: bool = False


@dataclass(frozen=True)
class Focus:
    """Điểm phóng to trên ảnh: {x, y} theo tỉ lệ 0-1 và scale 1-2.5."""


@dataclass(frozen=True)
class Image:
    """Đường dẫn file ảnh trên máy."""


@dataclass(frozen=True)
class SceneType:
    label: str
    purpose: str
    fields: dict = field(default_factory=dict)


ICON = Text(4, hint="1 emoji")
ACCENT = Choice(ACCENTS, "accent")
LINE1 = Text(32, required=True, hint="dòng 1 tiêu đề, ngắn")
LINE2 = Text(40, hint="dòng 2 tiêu đề, được nhấn màu")

SCENES: dict[str, SceneType] = {
    "hook": SceneType(
        "Mở đầu",
        "Cảnh đầu tiên: tiêu đề gây tò mò và vài thẻ chủ đề",
        {"tag": Text(24, hint="nhãn chủ đề nhỏ"), "line1": LINE1, "line2": LINE2, "accent": ACCENT,
         "chips": Items(4, 22)},
    ),
    "question": SceneType(
        "Câu hỏi",
        "Đặt vấn đề bằng một câu hỏi",
        {"icon": ICON, "line1": LINE1, "line2": LINE2, "accent": ACCENT, "sub": Text(110, hint="giải thích ngắn")},
    ),
    "stat": SceneType(
        "Con số",
        "Một con số ấn tượng chạy từ 0",
        {"tag": Text(24), "value": Number(required=True), "decimals": Number(integer=True),
         "prefix": Text(4), "suffix": Text(6, hint="đơn vị, VD: K, %, x"), "label": Text(40, required=True),
         "note": Text(80), "accent": ACCENT},
    ),
    "screenshot": SceneType(
        "Ảnh chụp",
        "Ảnh màn hình trong khung trình duyệt, có phóng vào chi tiết",
        {"line1": LINE1, "line2": LINE2, "accent": ACCENT, "url": Text(60, hint="địa chỉ hiển thị trên thanh trình duyệt"),
         "image": Image(), "focus": Focus(), "caption": Text(40, hint="nhãn dưới ảnh"), "caption_icon": ICON},
    ),
    "steps": SceneType(
        "Các bước",
        "Danh sách các bước hoặc cách áp dụng, đánh số",
        {"tag": Text(24), "line1": LINE1, "line2": LINE2, "accent": ACCENT, "items": Items(5, 56, min_items=2)},
    ),
    "diagram": SceneType(
        "Sơ đồ",
        "Luồng A → B → C",
        {"line1": LINE1, "line2": LINE2, "accent": ACCENT, "nodes": Items(4, 36, min_items=2)},
    ),
    "warning": SceneType(
        "Lưu ý",
        "Mẹo, cảnh báo hoặc điều cần tránh",
        {"level": Choice(LEVELS, "warning"), "icon": ICON, "title": Text(40, required=True),
         "text": Text(150), "bullets": Items(3, 56, plain=True)},
    ),
    "summary": SceneType(
        "Tóm tắt",
        "Gói lại các ý chính trước khi kết thúc",
        {"line1": LINE1, "line2": LINE2, "accent": ACCENT, "items": Items(5, 44, min_items=2, plain=True)},
    ),
    "cta": SceneType(
        "Kêu gọi",
        "Cảnh cuối: câu hỏi gợi bình luận và nút theo dõi",
        {"question": Text(70, required=True), "hint": Text(50), "button": Text(24), "button_icon": ICON},
    ),
}


def _cut(text: str, limit: int) -> str:
    """Cắt ở ranh giới từ và thêm dấu …"""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0] if " " in text[: limit - 1] else text[: limit - 1]
    return cut.rstrip(",.;: ") + "…"


def _clean_items(spec: Items, value, name: str, problems: list[str]) -> list:
    if not isinstance(value, list):
        value = []
    out = []
    for it in value:
        if spec.plain:
            text = it if isinstance(it, str) else (it.get("text", "") if isinstance(it, dict) else "")
            if text.strip():
                out.append(_cut(text.strip(), spec.text_len))
        elif isinstance(it, (dict, str)):
            d = it if isinstance(it, dict) else {"text": it}
            text = str(d.get("text", "")).strip()
            if text:
                out.append({"icon": _cut(str(d.get("icon", "")).strip(), 4), "text": _cut(text, spec.text_len)})
    if len(out) > spec.max_items:
        problems.append(f"{name}: tối đa {spec.max_items} mục, đã bỏ bớt.")
        out = out[: spec.max_items]
    if len(out) < spec.min_items:
        problems.append(f"{name}: cần ít nhất {spec.min_items} mục.")
    return out


def clean_scene(scene_type: str, data: dict) -> tuple[dict, list[str]]:
    """Trả về (dữ liệu đã làm gọn, danh sách vấn đề)."""
    spec = SCENES.get(scene_type)
    if spec is None:
        return {}, [f"Không có loại cảnh: {scene_type}"]
    data = data if isinstance(data, dict) else {}
    out: dict = {}
    problems: list[str] = []
    for name, f in spec.fields.items():
        value = data.get(name)
        if isinstance(f, Text):
            text = str(value).strip() if value is not None else ""
            if len(text) > f.max_len:
                problems.append(f"{name}: dài quá {f.max_len} ký tự, đã cắt.")
                text = _cut(text, f.max_len)
            if f.required and not text:
                problems.append(f"{name}: còn trống.")
            if text:
                out[name] = text
        elif isinstance(f, Choice):
            out[name] = value if value in f.values else f.default
        elif isinstance(f, Number):
            try:
                num = float(str(value).replace(",", ".")) if value not in (None, "") else None
            except ValueError:
                num = None
            if num is None:
                if f.required:
                    problems.append(f"{name}: cần một con số.")
            else:
                out[name] = int(num) if f.integer else num
        elif isinstance(f, Items):
            items = _clean_items(f, value, name, problems)
            if items:
                out[name] = items
        elif isinstance(f, Focus) and isinstance(value, dict):
            try:
                out[name] = {
                    "x": min(1.0, max(0.0, float(value.get("x", 0.5)))),
                    "y": min(1.0, max(0.0, float(value.get("y", 0.3)))),
                    "scale": min(2.5, max(1.0, float(value.get("scale", 1.0)))),
                }
            except (TypeError, ValueError):
                pass
        elif isinstance(f, Image) and isinstance(value, str) and value.strip():
            out[name] = value.strip()
    return out, problems


def describe_for_prompt() -> str:
    """Mô tả các loại cảnh và trường dữ liệu, chèn vào câu lệnh cho AI."""
    lines = []
    for key, spec in SCENES.items():
        parts = []
        for name, f in spec.fields.items():
            if isinstance(f, Text):
                parts.append(f"{name} (chữ ≤{f.max_len}{', bắt buộc' if f.required else ''}{', ' + f.hint if f.hint else ''})")
            elif isinstance(f, Choice):
                parts.append(f"{name} (một trong: {', '.join(f.values)})")
            elif isinstance(f, Number):
                parts.append(f"{name} (số{', bắt buộc' if f.required else ''})")
            elif isinstance(f, Items):
                kind = "danh sách chữ" if f.plain else "danh sách {icon: emoji, text}"
                parts.append(f"{name} ({kind}, {f.min_items}-{f.max_items} mục, mỗi mục ≤{f.text_len} ký tự)")
            elif isinstance(f, Focus):
                parts.append(f"{name} ({{x, y}} 0-1 và scale 1-2.5, điểm cần phóng to trên ảnh, không bắt buộc)")
        lines.append(f'- "{key}" ({spec.label}): {spec.purpose}. Trường: ' + "; ".join(parts))
    return "\n".join(lines)
