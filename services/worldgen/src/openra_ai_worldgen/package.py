from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .models import GeoSelection
from .raster import TerrainPlan
from .scenarios import mission_blueprint, scenario_manifest
from .terrain import TerrainView

GENERATOR_VERSION = "0.4.0"


def artifact_paths(selection: GeoSelection, output_directory: Path) -> tuple[Path, Path, Path]:
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    slug = "".join(c.lower() if c.isalnum() else "-" for c in selection.title).strip("-") or "earth-skirmish"
    slug = "-".join(filter(None, slug.split("-")))[:48]
    stem = f"{slug}-{selection.seed}"
    return (
        output_directory / f"{stem}.oramap",
        output_directory / f"{stem}.png",
        output_directory / f"{stem}.manifest.json",
    )


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def _fluent_value(value: str) -> str:
    """Keep generated story text on one safe Fluent line."""
    return " ".join(value.replace("{", "(").replace("}", ")").split())[:500]


def _mission_files(selection: GeoSelection) -> dict[str, bytes]:
    """Build a complete deterministic objective/story runtime for generated maps."""
    blueprint = mission_blueprint(selection.scenario_id)
    if blueprint and blueprint.objectives:
        primary = blueprint.objectives[0]
        secondary = blueprint.objectives[1] if len(blueprint.objectives) > 1 else "Preserve your combat strength."
        situation = blueprint.situation
    else:
        objective_by_archetype = {
            "river-crossing": "Secure both approaches and break the opposing force.",
            "urban-siege": "Establish a foothold and defeat the opposing force.",
            "supply-raid": "Disrupt hostile supply operations and eliminate resistance.",
            "convoy-defense": "Hold the route and defeat the interdiction force.",
            "infrastructure-defense": "Protect the approaches and eliminate the attackers.",
            "balanced-skirmish": "Defeat the opposing command and retain the battlefield.",
        }
        primary = objective_by_archetype[selection.mission_archetype]
        secondary = "Keep a viable field force until the escalation phase ends."
        situation = selection.story_seed.strip() or (
            f"A fictional operation unfolds around {selection.location_name}. "
            "Both commands are racing to control the terrain."
        )

    fluent = (
        f"earth-mission-situation = {_fluent_value(situation)}\n"
        f"earth-mission-primary = {_fluent_value(primary)}\n"
        f"earth-mission-secondary = {_fluent_value(secondary)}\n"
        "earth-mission-phase-one = Phase I: establish your foothold and scout the approaches.\n"
        "earth-mission-phase-two = Phase II: enemy operations are escalating. Commit your reserves.\n"
        "earth-mission-phase-three = Phase III: break the opposing command to secure the operation.\n"
    )
    rules = """World:
\tLuaScript:
\t\tScripts: campaign.lua, utils.lua, earth-mission.lua
\tMissionData:
\t\tBriefing: earth-mission-situation
"""
    script = """PlayerOne = nil
PlayerTwo = nil
PlayerOneObjective = nil
PlayerTwoObjective = nil
PlayerOneSurvival = nil
PlayerTwoSurvival = nil
MissionStarted = false
MissionResolved = false

CompleteFor = function(winner, objective, loser, loserObjective)
\tif MissionResolved then return end
\tMissionResolved = true
\twinner.MarkCompletedObjective(objective)
\tloser.MarkFailedObjective(loserObjective)
end

Tick = function()
	if PlayerOne == nil or PlayerTwo == nil then return end
	if not MissionStarted then
		MissionStarted = not PlayerOne.HasNoRequiredUnits() and not PlayerTwo.HasNoRequiredUnits()
		return
	end
\tif MissionResolved then return end
\tif PlayerOne.HasNoRequiredUnits() then
\t\tCompleteFor(PlayerTwo, PlayerTwoObjective, PlayerOne, PlayerOneObjective)
\telseif PlayerTwo.HasNoRequiredUnits() then
\t\tCompleteFor(PlayerOne, PlayerOneObjective, PlayerTwo, PlayerTwoObjective)
\tend
end

WorldLoaded = function()
\tPlayerOne = Player.GetPlayer("Multi0")
\tPlayerTwo = Player.GetPlayer("Multi1")
\tInitObjectives(PlayerOne)
\tInitObjectives(PlayerTwo)
\tPlayerOneObjective = AddPrimaryObjective(PlayerOne, "earth-mission-primary")
\tPlayerTwoObjective = AddPrimaryObjective(PlayerTwo, "earth-mission-primary")
\tPlayerOneSurvival = AddSecondaryObjective(PlayerOne, "earth-mission-secondary")
\tPlayerTwoSurvival = AddSecondaryObjective(PlayerTwo, "earth-mission-secondary")
\tMedia.DisplayMessageToPlayer(PlayerOne, UserInterface.GetFluentMessage("earth-mission-situation"), "Mission")
\tMedia.DisplayMessageToPlayer(PlayerTwo, UserInterface.GetFluentMessage("earth-mission-situation"), "Mission")
\tMedia.DisplayMessageToPlayer(PlayerOne, UserInterface.GetFluentMessage("earth-mission-phase-one"), "Command")
\tMedia.DisplayMessageToPlayer(PlayerTwo, UserInterface.GetFluentMessage("earth-mission-phase-one"), "Command")
\tTrigger.AfterDelay(DateTime.Minutes(3), function()
\t\tMedia.DisplayMessageToPlayer(PlayerOne, UserInterface.GetFluentMessage("earth-mission-phase-two"), "Command")
\t\tMedia.DisplayMessageToPlayer(PlayerTwo, UserInterface.GetFluentMessage("earth-mission-phase-two"), "Command")
\tend)
\tTrigger.AfterDelay(DateTime.Minutes(7), function()
\t\tif not MissionResolved then
\t\t\tPlayerOne.MarkCompletedObjective(PlayerOneSurvival)
\t\t\tPlayerTwo.MarkCompletedObjective(PlayerTwoSurvival)
\t\t\tMedia.DisplayMessageToPlayer(PlayerOne, UserInterface.GetFluentMessage("earth-mission-phase-three"), "Command")
\t\t\tMedia.DisplayMessageToPlayer(PlayerTwo, UserInterface.GetFluentMessage("earth-mission-phase-three"), "Command")
\t\tend
\tend)
end
"""
    return {
        "rules.yaml": rules.encode("utf-8"),
        "earth-mission.lua": script.encode("utf-8"),
        "map.ftl": fluent.encode("utf-8"),
    }


def _merge_map_sources(text: str, key: str, leading: tuple[str, ...], trailing: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.*)$", re.MULTILINE)
    match = pattern.search(text)
    existing = [value.strip() for value in match.group(1).split(",") if value.strip()] if match else []
    required = {*leading, trailing}
    sources = [*leading, *(value for value in existing if value not in required), trailing]
    replacement = f"{key}: {', '.join(sources)}"
    if match:
        return pattern.sub(replacement, text, count=1)
    return f"{text.rstrip()}\n\n{replacement}\n"


def _wire_mission_runtime(map_yaml: bytes) -> bytes:
    text = map_yaml.decode("utf-8")
    text = _merge_map_sources(
        text,
        "Rules",
        (
            "ra|rules/campaign-rules.yaml",
            "ra|rules/campaign-tooltips.yaml",
            "ra|rules/campaign-palettes.yaml",
        ),
        "rules.yaml",
    )
    text = _merge_map_sources(
        text,
        "FluentMessages",
        ("ra|fluent/lua.ftl", "ra|fluent/campaign.ftl"),
        "map.ftl",
    )
    return text.encode("utf-8")


def finalize_native_package(
    selection: GeoSelection,
    plan: TerrainPlan,
    package_path: Path,
    output_directory: Path,
    source_status: str,
    native: dict,
    native_options: dict,
    validation: dict,
    terrain_view: TerrainView | None = None,
) -> tuple[Path, Path, Path]:
    """Add Earth provenance to a package already rendered by OpenRA itself."""
    expected_package, preview_path, manifest_path = artifact_paths(selection, output_directory)
    if package_path.resolve() != expected_package.resolve():
        raise ValueError("native generator wrote an unexpected package path")

    with ZipFile(package_path, "r") as archive:
        original_entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
        map_yaml = _wire_mission_runtime(archive.read("map.yaml"))
        map_binary = archive.read("map.bin")
        preview = archive.read("map.png")

    blueprint = mission_blueprint(selection.scenario_id)
    if blueprint:
        objectives = "\n".join(f"{index}. {objective}" for index, objective in enumerate(blueprint.objectives, 1))
        sources = "\n".join(
            f"- {source.publisher}, {source.published}: {source.title} ({source.url})"
            for source in blueprint.sources
        )
        briefing_text = (
            f"# {blueprint.title}\n\n"
            f"## Situation\n\n{blueprint.situation}\n\n"
            f"## Objectives\n\n{objectives}\n\n"
            f"## Source boundary\n\nFactual cutoff: {blueprint.factual_cutoff}. "
            "Objectives, force composition, timing, distances, and outcomes are authored gameplay abstractions.\n\n"
            f"## Sources\n\n{sources}\n"
        )
    else:
        briefing_text = (
            f"# {selection.title}\n\n"
            f"A two-player skirmish inspired by terrain evidence around {selection.location_name} "
            f"({selection.latitude:.5f}, {selection.longitude:.5f}).\n\n"
            f"{selection.story_seed.strip() or 'Secure the approaches, protect your supply line, and control the center.'}\n\n"
            "OpenRA's native generator converts that terrain character into a mechanically playable battlefield. "
            "This is a stylized fictional scenario, not a factual simulation of people or events.\n"
        )
    briefing = briefing_text.encode("utf-8")
    mission_files = _mission_files(selection)
    checksums = {
        "map.yaml": hashlib.sha256(map_yaml).hexdigest(),
        "map.bin": hashlib.sha256(map_binary).hexdigest(),
        "map.png": hashlib.sha256(preview).hexdigest(),
    }
    if terrain_view:
        checksums["earth-terrain.png"] = hashlib.sha256(terrain_view.image).hexdigest()
    for name, content in mission_files.items():
        checksums[name] = hashlib.sha256(content).hexdigest()

    effective_player_faction = blueprint.player_faction if blueprint else selection.player_faction
    effective_opponent_faction = blueprint.opponent_faction if blueprint else selection.opponent_faction
    manifest = {
        "schema": "openra-ai.mission-package/v1",
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "selection": selection.as_dict(),
        "projection": "Earth evidence to native OpenRA generator profile",
        "source": {
            "provider": "OpenStreetMap",
            "attribution": "© OpenStreetMap contributors",
            "status": source_status,
            "feature_count": plan.source_feature_count,
        },
        "terrain_view": terrain_view.metadata() if terrain_view else {"provider": "unavailable"},
        "analysis": plan.analysis.as_dict(),
        "game": {"mod": "ra", "map_format": 12, "tileset": native.get("tileset", plan.tileset)},
        "generator": {
            "engine": "OpenRA ClassicMapGenerator",
            "engine_generator": native.get("engine_generator", "classic"),
            "requested_seed": native.get("requested_seed", selection.seed),
            "actual_seed": native.get("actual_seed", selection.seed),
            "uid": native.get("uid", ""),
            "options": native_options,
            "passability": native.get("passability", {}),
        },
        "design": {
            "feature_counts": plan.feature_counts,
            "mode": selection.generation_mode,
            "terrain_profile": native_options.get("terrain", "Plots"),
            "roads": native_options.get("roads", True),
            "mission_archetype": selection.mission_archetype,
            "player_faction": effective_player_faction,
            "opponent_faction": effective_opponent_faction,
        },
        "scenario": scenario_manifest(selection.scenario_id),
        "checksums": checksums,
        "validation": validation,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    replaced_names = {
        "map.yaml",
        "briefing.md",
        "openra-ai-manifest.json",
        "earth-terrain.png",
        *mission_files,
    }
    temporary_package = package_path.with_name(f".{package_path.name}.tmp")
    try:
        with ZipFile(temporary_package, "w", compression=ZIP_DEFLATED) as archive:
            for info, content in original_entries:
                if info.filename == "map.yaml":
                    archive.writestr(info, map_yaml)
                elif info.filename not in replaced_names:
                    archive.writestr(info, content)
            archive.writestr(_zip_info("briefing.md"), briefing)
            archive.writestr(_zip_info("openra-ai-manifest.json"), manifest_bytes)
            for name, content in mission_files.items():
                archive.writestr(_zip_info(name), content)
            if terrain_view:
                archive.writestr(_zip_info("earth-terrain.png"), terrain_view.image)
        temporary_package.replace(package_path)
    finally:
        temporary_package.unlink(missing_ok=True)

    preview_path.write_bytes(preview)
    manifest_path.write_bytes(manifest_bytes)
    return package_path, preview_path, manifest_path
