"""Kịch bản của một video ngắn: tiêu đề, các cảnh, lời đọc và nguồn hình cho từng cảnh."""

from dataclasses import asdict, dataclass, field

from app.render.scenes import SCENES, clean_scene

VISUAL_KINDS = {
    "none": "Không dùng ảnh",
    "source": "Khung hình từ video gốc",
    "web": "Chụp trang web",
    "file": "Ảnh bạn chọn",
}


@dataclass
class Visual:
    kind: str = "none"
    time: float | None = None  # giây trong video gốc (kind = source)
    url: str = ""  # kind = web
    path: str = ""  # ảnh đã chuẩn bị xong (khung hình đã tách, ảnh đã chụp, hoặc ảnh bạn chọn)


@dataclass
class Scene:
    type: str
    narration: str = ""
    data: dict = field(default_factory=dict)
    visual: Visual = field(default_factory=Visual)

    def problems(self) -> list[str]:
        _, problems = clean_scene(self.type, self.data)
        if not self.narration.strip():
            problems.append("Chưa có lời đọc.")
        return problems


@dataclass
class Script:
    title: str
    scenes: list[Scene] = field(default_factory=list)
    summary: str = ""
    start: float = 0.0  # đoạn trong video gốc mà kịch bản dựa vào
    end: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Script":
        scenes = []
        for s in d.get("scenes") or []:
            if not isinstance(s, dict) or s.get("type") not in SCENES:
                continue
            v = s.get("visual") if isinstance(s.get("visual"), dict) else {}
            time = v.get("time")
            visual = Visual(
                kind=v.get("kind") if v.get("kind") in VISUAL_KINDS else "none",
                time=float(time) if isinstance(time, (int, float)) else None,
                url=str(v.get("url") or ""),
                path=str(v.get("path") or ""),
            )
            data = s.get("data") if isinstance(s.get("data"), dict) else {}
            scenes.append(Scene(s["type"], str(s.get("narration") or ""), data, visual))
        return cls(
            title=str(d.get("title") or "Video chưa đặt tên"),
            scenes=scenes,
            summary=str(d.get("summary") or ""),
            start=float(d.get("start") or 0),
            end=float(d.get("end") or 0),
        )

    def problems(self) -> list[str]:
        out = []
        if not self.scenes:
            out.append("Kịch bản chưa có cảnh nào.")
        for i, s in enumerate(self.scenes, 1):
            out += [f"Cảnh {i} ({SCENES[s.type].label}): {p}" for p in s.problems()]
        return out

    def narration_words(self) -> int:
        return sum(len(s.narration.split()) for s in self.scenes)
