from app.pipeline.script import Scene, Script, Visual
from app.render.sample import sample_script
from app.render.scenes import SCENES, clean_scene, describe_for_prompt


def test_clean_scene_trims_and_reports():
    data, problems = clean_scene("hook", {
        "line1": "Một tiêu đề cực kỳ dài vượt quá giới hạn cho phép của dòng một",
        "accent": "màu lạ", "chips": [{"icon": "🎯", "text": "a"}] * 6, "rác": 1,
    })
    assert data["line1"].endswith("…") and len(data["line1"]) <= 32
    assert data["accent"] == "accent"
    assert len(data["chips"]) == 4
    assert "rác" not in data
    assert any("line1" in p for p in problems) and any("chips" in p for p in problems)


def test_clean_scene_types():
    data, problems = clean_scene("stat", {"value": "1,5", "label": "lần", "decimals": "1"})
    assert data["value"] == 1.5 and data["decimals"] == 1 and not problems
    _, problems = clean_scene("stat", {"label": "x"})
    assert any("value" in p for p in problems)

    data, _ = clean_scene("screenshot", {"line1": "a", "focus": {"x": 2, "y": -1, "scale": 9}})
    assert data["focus"] == {"x": 1.0, "y": 0.0, "scale": 2.5}

    data, problems = clean_scene("summary", {"line1": "a", "items": ["một", {"text": "hai"}, ""]})
    assert data["items"] == ["một", "hai"] and not problems

    assert clean_scene("khong-co", {})[1]


def test_prompt_describes_every_scene():
    text = describe_for_prompt()
    for key in SCENES:
        assert f'"{key}"' in text


def test_script_roundtrip_and_problems():
    script = sample_script()
    assert not script.problems()
    again = Script.from_dict(script.to_dict())
    assert again == script

    bad = Script.from_dict({"title": "x", "scenes": [
        {"type": "steps", "data": {"line1": "a"}, "visual": {"kind": "source", "time": 12}},
        {"type": "không có"},
    ]})
    assert len(bad.scenes) == 1
    assert bad.scenes[0].visual == Visual("source", 12.0)
    problems = bad.problems()
    assert any("items" in p for p in problems) and any("lời đọc" in p for p in problems)


def test_scene_problems_need_narration():
    assert "Chưa có lời đọc." in Scene("hook", "", {"line1": "a"}).problems()
