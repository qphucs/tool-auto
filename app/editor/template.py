"""Mẫu phong cách: mọi thứ đo được từ video mẫu cộng với tùy chỉnh của bạn."""

from dataclasses import asdict, dataclass, field, fields

FRAMING_LABELS = {
    "crop": "Cắt cho đầy khung",
    "blur": "Nền mờ",
    "pad": "Viền đen",
}


@dataclass
class TextStyle:
    font_size: int = 64  # cỡ chữ tính cho video rộng 1080px, tự co giãn theo kích thước thật
    color: str = "#FFFFFF"
    position: str = "top"  # top | center | bottom
    box: bool = True
    seconds: float = 0  # 0 = hiện suốt video


@dataclass
class SubtitleStyle:
    size: str = "medium"  # small | medium | large
    position: str = "bottom"  # bottom | middle | top


@dataclass
class TemplateSpec:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    framing: str = "crop"
    shot_durations: list[float] = field(default_factory=list)
    duration: float = 0
    brightness: float | None = None  # độ sáng trung bình (YAVG, 0-255)
    saturation: float | None = None  # độ đậm màu trung bình (SATAVG)
    match_color: bool = True
    zoom: bool = False
    fade: bool = False
    keep_audio: bool = True
    text: TextStyle = field(default_factory=TextStyle)
    subtitle: SubtitleStyle = field(default_factory=SubtitleStyle)
    sample_file: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TemplateSpec":
        def pick(klass, d: dict) -> dict:
            names = {f.name for f in fields(klass)}
            return {k: v for k, v in (d or {}).items() if k in names}

        top = pick(cls, data)
        top["text"] = TextStyle(**pick(TextStyle, data.get("text")))
        top["subtitle"] = SubtitleStyle(**pick(SubtitleStyle, data.get("subtitle")))
        return cls(**top)

    def copy(self) -> "TemplateSpec":
        return TemplateSpec.from_dict(self.to_dict())

    @property
    def orientation(self) -> str:
        if self.width == self.height:
            return "vuông"
        return "dọc" if self.height > self.width else "ngang"

    def summary(self) -> str:
        shots = self.shot_durations
        parts = [f"{self.width}x{self.height} ({self.orientation})", f"{self.fps} fps", f"dài {self.duration:.1f} giây"]
        if shots:
            parts.append(f"{len(shots)} cảnh, trung bình {sum(shots) / len(shots):.1f} giây/cảnh")
        parts.append(f"khung hình: {FRAMING_LABELS.get(self.framing, self.framing)}")
        if self.brightness is not None and self.saturation is not None:
            parts.append(f"độ sáng {self.brightness / 255:.0%}, độ đậm màu {self.saturation:.0f}")
        return " · ".join(parts)
