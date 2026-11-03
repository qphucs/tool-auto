"""Tạo trang HTML cho một cảnh: khung chung + dữ liệu cảnh dạng JSON."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from app.core.settings import BrandSettings
from app.render.scenes import SCENES

ASSETS = Path(__file__).parent / "assets"
ASSET_FILES = ("runtime.js", "theme.css", "scenes.js", "boot.js")


def even_captions(text: str, start: float, end: float) -> list[dict]:
    """Chia thời gian cho từng từ theo độ dài chữ. Dùng khi chưa có mốc thời gian thật từ giọng đọc."""
    words = text.split()
    if not words or end <= start:
        return []
    weights = [len(w) + 2 for w in words]
    total = sum(weights)
    out, t = [], start
    for w, weight in zip(words, weights):
        d = (end - start) * weight / total
        out.append({"w": w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def _hex_to_rgb(color: str) -> str:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return ", ".join(str(int(c[i : i + 2], 16)) for i in (0, 2, 4))
    except ValueError:
        return "79, 140, 255"


def brand_payload(brand: BrandSettings) -> dict:
    logo = Path(brand.logo) if brand.logo else None
    return {
        "vars": {
            "bg1": brand.bg1,
            "bg2": brand.bg2,
            "text": brand.text,
            "muted": brand.muted,
            "accent": brand.accent,
            "accent-2": brand.accent2,
            "accent-3": brand.accent3,
            "accent-4": brand.accent4,
            "glow": _hex_to_rgb(brand.accent),
            "font": f'"{brand.font}", "Segoe UI", Arial, sans-serif',
        },
        "channel": brand.channel,
        "logo": logo.as_uri() if logo and logo.is_file() else "",
        "show_logo": brand.show_logo,
    }


def _image_to_uri(data: dict) -> dict:
    image = data.get("image")
    if image and not str(image).startswith("file:"):
        p = Path(image)
        data = dict(data, image=p.as_uri() if p.is_file() else "")
    return data


@lru_cache(maxsize=1)
def assets_version() -> str:
    """Đổi khi sửa giao diện cảnh, để bộ nhớ đệm dựng lại cảnh."""
    h = hashlib.sha1()
    for name in ASSET_FILES:
        h.update((ASSETS / name).read_bytes())
    return h.hexdigest()[:12]


def build_page(
    scene: str, data: dict, duration: float, out: Path, captions: list[dict] | None = None,
    brand: dict | None = None, seed: int = 7, bg_offset: float = 0.0,
) -> Path:
    if scene not in SCENES:
        raise ValueError(f"Không có loại cảnh: {scene}")
    payload = {
        "type": scene,
        "duration": duration,
        "data": _image_to_uri(data),
        "captions": captions or [],
        "brand": brand or brand_payload(BrandSettings()),
        "seed": seed,
        "bgOffset": bg_offset,
    }
    # Chặn "</script>" trong dữ liệu làm vỡ trang
    data_js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<base href="{ASSETS.as_uri()}/">
<link rel="stylesheet" href="theme.css">
</head>
<body>
<canvas id="bg"></canvas>
<div id="brand"></div>
<div id="stage"></div>
<div id="captions"></div>
<script src="runtime.js"></script>
<script src="scenes.js"></script>
<script>window.__SCENE = {data_js};</script>
<script src="boot.js"></script>
</body>
</html>
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
