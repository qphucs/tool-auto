"""Dựng video thành phẩm bằng FFmpeg.

Mỗi đoạn được dựng riêng (đổi khung hình, màu, zoom, mờ dần) với cùng thông số mã hóa,
rồi nối bằng concat, cuối cùng chèn chữ tiêu đề và phụ đề.
"""

import logging
import shutil
import textwrap
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.core.media import VideoInfo, probe
from app.editor import analyzer, planner, subtitles
from app.editor.ffmpeg import FFmpegError, run
from app.editor.planner import Segment
from app.editor.template import TemplateSpec

log = logging.getLogger(__name__)

Report = Callable[[float, str], None]

VIDEO_ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
AUDIO_ENC = ["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]
FADE = 0.15
ZOOM = 0.08  # phóng to thêm 8% trong mỗi cảnh
FONT_CANDIDATES = ("arialbd.ttf", "arial.ttf", "segoeuib.ttf", "segoeui.ttf")
SUB_SIZES = {"small": 0.04, "medium": 0.05, "large": 0.065}  # tỉ lệ so với chiều rộng video
SUB_ALIGN = {"bottom": 2, "middle": 5, "top": 8}  # căn lề kiểu ASS
SUB_MARGIN = {"bottom": 0.12, "middle": 0.0, "top": 0.10}  # tỉ lệ so với chiều cao video
TITLE_Y = {"top": "h*0.08", "center": "(h-text_h)/2", "bottom": "h*0.80-text_h"}


@dataclass
class RenderJob:
    spec: TemplateSpec
    sources: list[Path]
    out_dir: Path
    mode: str = "auto"
    clip_count: int = 0
    title: str = ""
    srt: Path | None = None


@dataclass
class RenderResult:
    outputs: list[Path]
    mode: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ColorAdjust:
    brightness: float
    saturation: float


def color_adjust(spec: TemplateSpec, stats: tuple[float, float] | None) -> ColorAdjust | None:
    if not spec.match_color or stats is None or spec.brightness is None or spec.saturation is None:
        return None
    src_y, src_s = stats
    b = max(-0.25, min(0.25, (spec.brightness - src_y) / 255))
    s = max(0.6, min(1.6, spec.saturation / src_s)) if src_s > 1 else 1.0
    if abs(b) < 0.01 and abs(s - 1) < 0.03:
        return None
    return ColorAdjust(round(b, 3), round(s, 3))


def video_chain(spec: TemplateSpec, duration: float, adjust: ColorAdjust | None) -> str:
    w, h, fps = spec.width, spec.height, spec.fps
    if spec.framing == "blur":
        head = (
            f"[0:v]split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=20:2[bg];"
            f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
    elif spec.framing == "pad":
        head = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
    else:
        head = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    chain = [head, "setsar=1"]
    if adjust:
        chain.append(f"eq=brightness={adjust.brightness}:saturation={adjust.saturation}")
    chain.append(f"fps={fps}")
    if spec.zoom:
        frames = max(1, round(duration * fps))
        chain.append(
            f"zoompan=z='1+{ZOOM}*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps}"
        )
    if spec.fade and duration > 4 * FADE:
        chain.append(f"fade=t=in:st=0:d={FADE},fade=t=out:st={duration - FADE:.3f}:d={FADE}")
    chain.append("format=yuv420p")
    return ",".join(chain) + "[v]"


def audio_chain(spec: TemplateSpec, duration: float) -> str:
    chain = ["aformat=channel_layouts=stereo", "aresample=44100", "apad"]
    if spec.fade and duration > 4 * FADE:
        chain += [f"afade=t=in:d={FADE}", f"afade=t=out:st={duration - FADE:.3f}:d={FADE}"]
    return ",".join(chain)


def title_filter(spec: TemplateSpec) -> str:
    style = spec.text
    size = round(style.font_size * spec.width / 1080)
    parts = [
        "drawtext=fontfile=font.ttf",
        "textfile=title.txt",
        "expansion=none",
        f"fontsize={size}",
        f"fontcolor={style.color}",
        "text_align=C",
        f"line_spacing={-size // 4}",  # drawtext để khoảng cách dòng khá rộng, kéo sát lại
        "x=(w-text_w)/2",
        f"y={TITLE_Y.get(style.position, TITLE_Y['top'])}",
    ]
    if style.box:
        parts += ["box=1", "boxcolor=black@0.55", f"boxborderw={size // 3}"]
    if style.seconds > 0:
        parts.append(f"enable='lte(t,{style.seconds})'")
    return ":".join(parts)


def wrap_title(spec: TemplateSpec, title: str) -> str:
    size = spec.text.font_size * spec.width / 1080
    per_line = max(8, int(spec.width * 0.86 / (size * 0.55)))
    return "\n".join(textwrap.wrap(title.strip(), per_line)) or title.strip()


def subtitle_filter(spec: TemplateSpec, srt_name: str) -> str:
    # libass tính cỡ chữ theo khung 288px chiều cao, đổi từ pixel thật sang đơn vị đó
    unit = 288 / spec.height
    pos = spec.subtitle.position if spec.subtitle.position in SUB_ALIGN else "bottom"
    font = round(spec.width * SUB_SIZES.get(spec.subtitle.size, 0.05) * unit, 1)
    margin = round(spec.height * SUB_MARGIN[pos] * unit)
    style = (
        f"FontName=Arial,FontSize={font},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline=1.2,Shadow=0,Alignment={SUB_ALIGN[pos]},MarginV={margin}"
    )
    return f"subtitles={srt_name}:charenc=UTF-8:force_style='{style}'"


def find_font() -> Path | None:
    fonts = Path("C:/Windows/Fonts")
    return next((fonts / n for n in FONT_CANDIDATES if (fonts / n).is_file()), None)


def _render_segment(
    spec: TemplateSpec, src: Path, info: VideoInfo, seg: Segment, adjust: ColorAdjust | None,
    out: Path, cancel: threading.Event | None,
) -> None:
    d = seg.duration
    args = ["-y", "-v", "error", "-ss", f"{seg.start:.3f}", "-t", f"{d:.3f}", "-i", str(src)]
    silent = spec.keep_audio and not info.has_audio
    if silent:  # video gốc không có tiếng: thêm tiếng im lặng để các đoạn nối được với nhau
        args += ["-f", "lavfi", "-t", f"{d:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    args += ["-filter_complex", video_chain(spec, d, adjust), "-map", "[v]"]
    if spec.keep_audio:
        args += ["-map", "1:a:0" if silent else "0:a:0", "-af", audio_chain(spec, d), *AUDIO_ENC]
    else:
        args.append("-an")
    args += [*VIDEO_ENC, "-r", str(spec.fps), "-t", f"{d:.3f}", str(out)]
    run(args, cancel=cancel)


def _finish(
    spec: TemplateSpec, work: Path, seg_files: list[str], index: int, title: str,
    cues: list[subtitles.Cue], out: Path, cancel: threading.Event | None,
) -> None:
    list_file = work / f"list_{index}.txt"
    list_file.write_text("".join(f"file '{name}'\n" for name in seg_files), encoding="utf-8")
    filters = []
    if cues:
        srt_name = f"subs_{index}.srt"
        (work / srt_name).write_text(subtitles.to_srt(cues), encoding="utf-8")
        filters.append(subtitle_filter(spec, srt_name))
    if title:
        filters.append(title_filter(spec))
    args = ["-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", list_file.name]
    if filters:
        args += ["-vf", ",".join(filters), *VIDEO_ENC, "-c:a", "copy"]
    else:
        args += ["-c", "copy"]
    args += ["-movflags", "+faststart", str(out)]
    try:
        run(args, cwd=work, cancel=cancel)
    except BaseException:
        out.unlink(missing_ok=True)
        raise


def render(job: RenderJob, report: Report = lambda f, m: None, cancel: threading.Event | None = None) -> RenderResult:
    spec = job.spec
    infos = [probe(p) for p in job.sources]
    for p, info in zip(job.sources, infos):
        if not info.duration or not info.width:
            raise FFmpegError(f"Không đọc được video gốc: {p.name}")
    src_durs = [info.duration for info in infos]
    mode = planner.resolve_mode(job.mode, spec, src_durs)
    warnings: list[str] = []

    cuts: list[float] = []
    if mode != "keep":
        offset = 0.0
        for i, (p, d) in enumerate(zip(job.sources, src_durs)):
            report(0.02 + 0.1 * i / len(job.sources), f"Đang tìm điểm chuyển cảnh: {p.name}")
            cuts += [offset + c for c in analyzer.detect_cuts(p, cancel)]
            offset += d

    adjusts: list[ColorAdjust | None] = [None] * len(job.sources)
    if spec.match_color and spec.brightness is not None:
        for i, p in enumerate(job.sources):
            report(0.12 + 0.08 * i / len(job.sources), f"Đang đo màu: {p.name}")
            adjusts[i] = color_adjust(spec, analyzer.color_stats(p, cancel))

    plans = planner.plan(mode, spec, src_durs, cuts, job.clip_count)

    cues: list[subtitles.Cue] = []
    if job.srt:
        if len(job.sources) > 1:
            warnings.append("Phụ đề .srt chỉ dùng được khi có đúng một video gốc nên đã bỏ qua.")
        else:
            cues = subtitles.parse_srt(job.srt.read_text(encoding="utf-8-sig", errors="replace"))

    title = job.title.strip()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job.out_dir.mkdir(parents=True, exist_ok=True)
    work = job.out_dir / "_work" / stamp
    work.mkdir(parents=True, exist_ok=True)
    if title:
        font = find_font()
        if font is None:
            warnings.append("Không tìm thấy font Arial hoặc Segoe UI nên bỏ qua chữ tiêu đề.")
            title = ""
        else:
            shutil.copy(font, work / "font.ttf")
            (work / "title.txt").write_text(wrap_title(spec, title), encoding="utf-8")

    stem = job.sources[0].stem
    total_steps = sum(len(p) for p in plans) + len(plans)
    done = 0
    outputs: list[Path] = []
    try:
        for k, segments in enumerate(plans):
            seg_files = []
            for j, seg in enumerate(segments):
                report(0.2 + 0.8 * done / total_steps, f"Video {k + 1}/{len(plans)}: dựng đoạn {j + 1}/{len(segments)}")
                name = f"seg_{k}_{j}.mp4"
                _render_segment(spec, job.sources[seg.source], infos[seg.source], seg, adjusts[seg.source], work / name, cancel)
                seg_files.append(name)
                done += 1
            report(0.2 + 0.8 * done / total_steps, f"Video {k + 1}/{len(plans)}: ghép và chèn chữ")
            suffix = f"-{k + 1}" if len(plans) > 1 else ""
            out = job.out_dir / f"{stem}-{stamp}{suffix}.mp4"
            _finish(spec, work, seg_files, k, title, subtitles.remap(cues, segments) if cues else [], out, cancel)
            outputs.append(out)
            done += 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    report(1.0, "Xong")
    log.info("Dựng xong %d video (%s) từ %s", len(outputs), mode, [p.name for p in job.sources])
    return RenderResult(outputs, mode, warnings)
