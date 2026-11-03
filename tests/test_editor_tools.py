"""Các công cụ video dùng lại cho tool mới: chạy FFmpeg, tìm chuyển cảnh, phụ đề."""

import shutil
import subprocess
import threading

import pytest

from app.editor.analyzer import detect_cuts
from app.editor.ffmpeg import Cancelled, FFmpegError, run
from app.editor.subtitles import Cue, parse_srt, to_srt

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="Cần ffmpeg")


def test_srt_roundtrip():
    text = "﻿1\r\n00:00:01,000 --> 00:00:03,000\r\nXin chào\r\n\r\n2\r\n00:00:05,500 --> 00:00:06,000\r\nTạm biệt\r\n"
    cues = parse_srt(text)
    assert cues == [Cue(1.0, 3.0, "Xin chào"), Cue(5.5, 6.0, "Tạm biệt")]
    assert parse_srt(to_srt(cues)) == cues


@needs_ffmpeg
def test_detect_cuts(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "color=c=red:s=160x90:r=10:d=1",
         "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10:d=1.5",
         "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(clip)],
        check=True,
    )
    assert detect_cuts(clip) == pytest.approx([1.0], abs=0.15)


@needs_ffmpeg
def test_run_errors_and_cancel(tmp_path):
    with pytest.raises(FFmpegError):
        run(["-v", "error", "-i", str(tmp_path / "missing.mp4"), "-f", "null", "-"])
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        run(["-version"], cancel=cancel)
