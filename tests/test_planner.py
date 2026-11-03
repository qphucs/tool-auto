import pytest

from app.editor import planner
from app.editor.planner import Segment, place_segments, sequence_durations
from app.editor.subtitles import Cue, parse_srt, remap, to_srt
from app.editor.template import TemplateSpec


def test_sequence_durations_repeats_rhythm():
    assert sequence_durations([1.0, 2.0], 5.0) == [1.0, 2.0, 1.0, 1.0]
    # đoạn cuối quá ngắn thì gộp vào đoạn trước
    assert sequence_durations([1.0], 2.1) == pytest.approx([1.0, 1.1])
    assert sequence_durations([], 3.0) == [3.0]


def test_place_segments_spread_in_order():
    segs = place_segments([1.0, 1.0], [10.0], [], 0.0, 10.0)
    assert segs == [Segment(0, 2.0, 1.0), Segment(0, 7.0, 1.0)]


def test_place_segments_snaps_to_cut():
    segs = place_segments([1.0, 1.0], [10.0], [2.6], 0.0, 10.0)
    assert segs[0].start == 2.6


def test_place_segments_never_crosses_files():
    segs = place_segments([3.0, 3.0], [4.0, 4.0], [], 0.0, 8.0)
    for s in segs:
        assert s.start + s.duration <= 4.0 + 1e-6
    assert {s.source for s in segs} == {0, 1}


def test_place_segments_too_long():
    assert place_segments([5.0, 5.0], [3.0], [], 0.0, 3.0) == [Segment(0, 0.0, 3.0)]


def test_resolve_mode_and_plans():
    spec = TemplateSpec(shot_durations=[1.0, 2.0], duration=10)
    assert planner.resolve_mode("auto", spec, [11.0]) == "keep"
    assert planner.resolve_mode("auto", spec, [60.0]) == "split"
    assert planner.resolve_mode("auto", spec, [20.0]) == "rhythm"
    assert planner.resolve_mode("auto", spec, [5.0, 5.0]) == "rhythm"

    assert planner.plan("keep", spec, [3.0, 4.0], []) == [[Segment(0, 0.0, 3.0)], [Segment(1, 0.0, 4.0)]]
    rhythm = planner.plan("rhythm", spec, [20.0], [])
    assert len(rhythm) == 1 and sum(s.duration for s in rhythm[0]) == pytest.approx(10)

    split = planner.plan("split", spec, [60.0], [])
    assert len(split) == 6
    for k, clip in enumerate(split):
        assert all(10 * k <= s.start < 10 * (k + 1) for s in clip)


def test_srt_roundtrip_and_remap():
    text = "﻿1\r\n00:00:01,000 --> 00:00:03,000\r\nXin chào\r\n\r\n2\r\n00:00:05,500 --> 00:00:06,000\r\nTạm biệt\r\n"
    cues = parse_srt(text)
    assert cues == [Cue(1.0, 3.0, "Xin chào"), Cue(5.5, 6.0, "Tạm biệt")]
    assert parse_srt(to_srt(cues)) == cues

    # Lấy đoạn 2-4s rồi 5-7s: câu 1 còn 0-1s, câu 2 thành 2.5-3s
    mapped = remap(cues, [Segment(0, 2.0, 2.0), Segment(0, 5.0, 2.0)])
    assert mapped == [Cue(0.0, 1.0, "Xin chào"), Cue(2.5, 3.0, "Tạm biệt")]
