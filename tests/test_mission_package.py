from openra_ai_worldgen.models import GeoSelection
from openra_ai_worldgen.package import _mission_files


def test_generated_mission_has_runtime_objectives_and_story_phases() -> None:
    files = _mission_files(
        GeoSelection(
            latitude=24.7136,
            longitude=46.6753,
            story_seed="A relief corridor is threatened.",
            mission_archetype="convoy-defense",
        )
    )

    assert set(files) == {"rules.yaml", "earth-mission.lua", "map.ftl"}
    assert b"LuaScript" in files["rules.yaml"]
    assert b"AddPrimaryObjective" in files["earth-mission.lua"]
    assert b"MarkCompletedObjective" in files["earth-mission.lua"]
    assert b"Phase III" in files["map.ftl"]
    assert b"A relief corridor is threatened." in files["map.ftl"]


def test_story_text_cannot_inject_fluent_syntax() -> None:
    files = _mission_files(
        GeoSelection(latitude=0, longitude=0, story_seed="Hold { $unsafe }\nthen advance")
    )
    assert b"{" not in files["map.ftl"]
    assert b"then advance" in files["map.ftl"]
