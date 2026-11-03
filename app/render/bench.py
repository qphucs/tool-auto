"""Đo tốc độ dựng HTML → video trên máy này.

Chạy: .venv\\Scripts\\python.exe -m app.render.bench [thư mục kết quả]
"""

import json
import sys
import threading
from pathlib import Path

from app.render.html_renderer import METHODS, FrameJob, RenderStats, render
from app.render.page import build_page, even_captions

DEMO_DURATION = 10.0
BENCH_SECONDS = 3.0
SIZES = ((540, 960), (1080, 1920))
WORKER_COUNTS = (1, 3)

DEMO_DATA = {
    "tag": "Mẹo AI",
    "line1": "Viết prompt",
    "line2": "chuẩn trong 30 giây",
    "accent": "accent",
    "chips": [
        {"icon": "🎯", "text": "Rõ mục tiêu"},
        {"icon": "🧩", "text": "Đủ bối cảnh"},
        {"icon": "📐", "text": "Định dạng"},
        {"icon": "🔁", "text": "Sửa dần"},
    ],
}
DEMO_CAPTION = "Chỉ cần bốn bước này là AI hiểu đúng ý bạn ngay từ lần đầu tiên"


def demo_page(work: Path, duration: float = DEMO_DURATION) -> Path:
    return build_page("hook", DEMO_DATA, duration, work / "demo.html", even_captions(DEMO_CAPTION, 0.6, duration - 0.8))


def render_demo(out_dir: Path, report=None, cancel: threading.Event | None = None,
                method: str = "cdp_jpeg", workers: int = 3) -> tuple[Path, RenderStats]:
    """Dựng video thử 10 giây ở 1080x1920."""
    page = demo_page(out_dir / "_bench")
    out = out_dir / "video-thu-10s.mp4"
    stats = render(FrameJob(page, DEMO_DURATION, 1080, 1920), out, method, workers, report, cancel)
    return out, stats


def run_bench(out_dir: Path, log=print) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    page = demo_page(out_dir / "_bench", BENCH_SECONDS)
    results = []
    for width, height in SIZES:
        for method in METHODS:
            for workers in WORKER_COUNTS:
                stats = render(FrameJob(page, BENCH_SECONDS, width, height), out_dir / "_bench" / "b.mp4", method, workers)
                results.append(stats)
                log(f"{width}x{height}  {method:9s} x{workers}:  {stats.render_fps:5.1f} khung/giây, "
                    f"{stats.realtime_factor:4.2f} giây dựng / 1 giây video")

    best = {}
    for width, height in SIZES:
        same = [r for r in results if (r.width, r.height) == (width, height)]
        best[f"{width}x{height}"] = min(same, key=lambda r: r.seconds)

    final = best["1080x1920"]
    log(f"\nDựng video thử {DEMO_DURATION:.0f} giây 1080x1920 bằng cách nhanh nhất ({final.method} x{final.workers})...")
    video, demo = render_demo(out_dir, method=final.method, workers=final.workers)
    log(f"Xong: {video}  ({demo.seconds:.1f} giây, {demo.realtime_factor:.2f} giây dựng / 1 giây video)")

    summary = {
        "results": [r.__dict__ | {"render_fps": r.render_fps, "realtime_factor": r.realtime_factor} for r in results],
        "best": {k: v.__dict__ for k, v in best.items()},
        "demo": demo.__dict__ | {"realtime_factor": demo.realtime_factor, "video": str(video)},
    }
    (out_dir / "bench.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    run_bench(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("bench-output"))
