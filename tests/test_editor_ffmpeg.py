"""Phân tích và dựng video thật bằng FFmpeg trên các clip nhỏ tự tạo."""

import shutil
import subprocess
import threading

import pytest

from app.core.media import probe
from app.editor import analyzer
from app.editor.ffmpeg import Cancelled
from app.editor.renderer import RenderJob, render

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="Cần ffmpeg")


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    sample = d / "mau.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "color=c=red:s=360x640:r=10:d=1",
        "-f", "lavfi", "-i", "color=c=blue:s=360x640:r=10:d=1.5",
        "-f", "lavfi", "-i", "color=c=green:s=360x640:r=10:d=1",
        "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-pix_fmt", "yuv420p", str(sample),
    )
    source = d / "goc.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=8",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
        "-shortest", "-pix_fmt", "yuv420p", str(source),
    )
    silent = d / "khong-tieng.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=4", "-pix_fmt", "yuv420p", str(silent))
    srt = d / "phude.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:08,000\nXin chào các bạn\n", encoding="utf-8")
    return {"sample": sample, "source": source, "silent": silent, "srt": srt}


@pytest.fixture(scope="module")
def spec(clips):
    return analyzer.analyze_sample(clips["sample"])


def test_analyze_sample(spec, clips):
    assert spec.shot_durations == pytest.approx([1.0, 1.5, 1.0], abs=0.15)
    assert (spec.width, spec.height) == (720, 1280)  # cạnh ngắn nâng lên tối thiểu 720
    assert spec.duration == pytest.approx(3.5, abs=0.1)
    assert spec.framing == "crop"
    assert spec.brightness is not None and spec.saturation is not None
    assert spec.sample_file == str(clips["sample"])


def test_render_rhythm_with_title_and_subtitles(spec, clips, tmp_path):
    job = RenderJob(spec=spec, sources=[clips["source"]], out_dir=tmp_path, mode="rhythm",
                    title="Tiêu đề thử nghiệm có dấu tiếng Việt khá dài để xuống dòng", srt=clips["srt"])
    progress = []
    result = render(job, lambda f, m: progress.append(f))
    assert result.mode == "rhythm" and not result.warnings
    [out] = result.outputs
    info = probe(out)
    assert (info.width, info.height) == (720, 1280)
    assert info.duration == pytest.approx(3.5, abs=0.3)
    assert info.has_audio
    assert progress[-1] == 1.0
    assert not (tmp_path / "_work").exists() or not any((tmp_path / "_work").iterdir())


def test_render_split_blur_zoom_fade(spec, clips, tmp_path):
    s = spec.copy()
    s.framing, s.zoom, s.fade = "blur", True, True
    result = render(RenderJob(spec=s, sources=[clips["source"]], out_dir=tmp_path, mode="split", clip_count=2))
    assert len(result.outputs) == 2
    for out in result.outputs:
        assert probe(out).duration == pytest.approx(3.5, abs=0.3)


def test_render_keep_mixed_sources_muted(spec, clips, tmp_path):
    s = spec.copy()
    s.keep_audio = False
    s.framing = "pad"
    job = RenderJob(spec=s, sources=[clips["source"], clips["silent"]], out_dir=tmp_path, mode="keep", srt=clips["srt"])
    result = render(job)
    assert len(result.outputs) == 2
    assert result.warnings  # srt bị bỏ qua vì có 2 video gốc
    assert not probe(result.outputs[0]).has_audio


def test_render_silent_source_keeps_audio_track(spec, clips, tmp_path):
    result = render(RenderJob(spec=spec, sources=[clips["silent"], clips["source"]], out_dir=tmp_path, mode="rhythm"))
    assert probe(result.outputs[0]).has_audio


def test_cancel(spec, clips, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        render(RenderJob(spec=spec, sources=[clips["source"]], out_dir=tmp_path, mode="rhythm"), cancel=cancel)
