import shutil
import subprocess

import pytest

from app.core.media import VideoInfo, probe


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="Cần ffmpeg")
def test_probe_vertical_clip(tmp_path):
    path = tmp_path / "v.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=360x640:rate=10:duration=2", str(path)],
        check=True,
    )
    info = probe(path)
    assert (info.width, info.height) == (360, 640)
    assert info.duration == pytest.approx(2, abs=0.2)
    assert info.is_vertical
    assert info.describe() == "360x640 · dọc · 00:02"


def test_probe_bad_file(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"xx")
    assert probe(bad) == VideoInfo()
    assert VideoInfo().describe() == "Không đọc được thông tin video."
