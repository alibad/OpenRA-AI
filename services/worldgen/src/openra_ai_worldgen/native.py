from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import subprocess
from typing import Any

from .models import GeoSelection, TerrainAnalysis


@dataclass(frozen=True)
class NativeMapResult:
    package_path: Path
    metadata: dict[str, Any]
    options: dict[str, str | int | bool]


def terrain_profile(analysis: TerrainAnalysis) -> str:
    """Translate Earth/vision evidence into a supported ClassicMapGenerator profile."""
    if analysis.water_confidence >= 0.70:
        return "MountainLakes" if analysis.relief == "mountainous" else "Lakes"
    if analysis.water_confidence >= 0.25:
        return "Puddles"
    if analysis.relief == "mountainous":
        return "Mountains"
    if analysis.relief == "rolling":
        return "Rocky"
    if analysis.urban_density >= 0.24:
        return "Plots"
    if analysis.vegetation_density >= 0.55:
        return "Woodlands"
    if analysis.vegetation_density >= 0.28:
        return "Parks"
    return "Plains"


def _seeded_choice(selection: GeoSelection, salt: int, choices: tuple[str, ...]) -> str:
    """Pick a stable recipe component without coupling it to Python's hash seed."""
    return choices[(selection.seed + salt) % len(choices)]


def _creative_terrain_choices(base: str, selection: GeoSelection, analysis: TerrainAnalysis) -> tuple[str, ...]:
    if selection.mission_archetype == "river-crossing":
        return ("NarrowWetlands", "Wetlands", "MountainLakes" if analysis.relief == "mountainous" else "Puddles")
    if selection.mission_archetype == "urban-siege":
        return ("Plots", "Gardens", "Rocky")
    if selection.mission_archetype == "supply-raid":
        return (base, "Plots", "Rocky")
    if selection.mission_archetype == "convoy-defense":
        return (base, "Rocky", "Plots")
    if selection.mission_archetype == "infrastructure-defense":
        return (base, "Plots", "Gardens")
    if analysis.water_confidence >= 0.25:
        return (base, "Wetlands", "Puddles")
    if analysis.relief == "mountainous":
        return (base, "Rocky", "MountainLakes")
    if analysis.vegetation_density >= 0.28:
        return (base, "Gardens", "Overgrown")
    return (base, "Plots", "Rocky")


def generation_options(selection: GeoSelection, analysis: TerrainAnalysis) -> dict[str, str | int | bool]:
    if analysis.urban_density >= 0.55:
        civilian_density = "High"
    elif analysis.urban_density >= 0.25:
        civilian_density = "Medium"
    elif analysis.urban_density >= 0.10:
        civilian_density = "Low"
    else:
        civilian_density = "None"

    base_terrain = terrain_profile(analysis)
    options: dict[str, str | int | bool] = {
        "tileset": {"desert": "DESERT", "snow": "SNOW"}.get(analysis.biome, "TEMPERAT"),
        "size": selection.map_size,
        "seed": selection.seed,
        "terrain": base_terrain,
        "shape": "Square",
        "players": 2,
        # Reality-first keeps natural asymmetry. The other modes use rotational
        # symmetry for tournament-grade economy and start fairness.
        "symmetry": "None" if selection.generation_mode == "reality-first" else "2Rotations",
        "resources": "Medium",
        "buildings": "Extra" if analysis.urban_density >= 0.45 else "Standard",
        "density": "AreaAndPlayers" if analysis.urban_density >= 0.30 else "Players",
        "civilian-density": civilian_density,
        "roads": True,
        "deny-walled-areas": True,
        "attempts": 8,
    }

    # Mission archetypes are gameplay recipes built from the native Random Map
    # controls. Reality-first preserves the observed terrain family; the other
    # modes are allowed to strengthen the requested tactical structure.
    if selection.mission_archetype == "river-crossing":
        if selection.generation_mode != "reality-first":
            options["terrain"] = "MountainLakes" if analysis.relief == "mountainous" else "NarrowWetlands"
        options["density"] = "AreaAndPlayers"
    elif selection.mission_archetype == "urban-siege":
        if selection.generation_mode != "reality-first":
            options["terrain"] = "Gardens" if analysis.vegetation_density >= 0.45 else "Plots"
        options["buildings"] = "Extra"
        options["density"] = "AreaHigh"
        options["civilian-density"] = "High"
    elif selection.mission_archetype == "supply-raid":
        options["resources"] = "VeryHigh"
        options["buildings"] = "OilRush"
        options["density"] = "AreaAndPlayers"
    elif selection.mission_archetype == "convoy-defense":
        options["resources"] = "High"
        options["buildings"] = "OilOnly"
        options["density"] = "AreaAndPlayers"
    elif selection.mission_archetype == "infrastructure-defense":
        if selection.generation_mode != "reality-first":
            options["terrain"] = "Plots"
        options["resources"] = "High"
        options["buildings"] = "Extra"
        options["density"] = "AreaAndPlayers"

    if selection.generation_mode == "creative-remix":
        options["terrain"] = _seeded_choice(
            selection,
            0,
            _creative_terrain_choices(base_terrain, selection, analysis),
        )
        shapes = ("Square",) if selection.mission_archetype in {"river-crossing", "urban-siege"} else (
            "Square",
            "CircleMountain",
            "CircleWater",
        )
        options["shape"] = _seeded_choice(selection, 11, shapes)
        options["symmetry"] = _seeded_choice(
            selection,
            23,
            ("2Rotations", "LeftMatchesRight", "TopMatchesBottom", "TopLeftMatchesBottomRight", "TopRightMatchesBottomLeft"),
        )
        options["attempts"] = 12

    return options


class NativeMapGenerator:
    def __init__(self, engine_root: Path | None = None):
        configured = os.environ.get("OPENRA_AI_ENGINE_DIR", "").strip()
        self.engine_root = (
            engine_root
            or (Path(configured) if configured else None)
            or Path(__file__).resolve().parents[4] / "engine" / "openra"
        ).resolve()

    @property
    def utility(self) -> Path:
        configured = os.environ.get("OPENRA_AI_UTILITY", "").strip()
        if configured:
            return Path(configured).expanduser().resolve()

        binary_name = "OpenRA.Utility.exe" if platform.system() == "Windows" else "OpenRA.Utility"
        candidates = [
            self.engine_root / "bin" / "OpenRA.Utility.exe",
            self.engine_root / "bin" / "OpenRA.Utility",
        ]
        architecture = platform.machine().lower()
        architecture = "arm64" if architecture in {"arm64", "aarch64"} else "x64"
        runtime_prefix = {"Darwin": "osx", "Windows": "win", "Linux": "linux"}.get(platform.system())
        if runtime_prefix:
            candidates.append(self.engine_root / "bin" / f"{runtime_prefix}-{architecture}" / binary_name)
        return next((candidate for candidate in candidates if candidate.is_file()), candidates[0])

    def generate(
        self,
        selection: GeoSelection,
        analysis: TerrainAnalysis,
        package_path: Path,
    ) -> NativeMapResult:
        if not self.utility.is_file():
            raise RuntimeError(
                f"OpenRA native map generator is unavailable at {self.utility}. "
                "Build the engine locally before generating Earth missions."
            )

        options = generation_options(selection, analysis)
        package_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.utility),
            "ra",
            "--generate-openra-ai-map",
            f"--output={package_path}",
            f"--tileset={options['tileset']}",
            f"--size={options['size']}",
            f"--seed={options['seed']}",
            f"--terrain={options['terrain']}",
            f"--shape={options['shape']}",
            f"--players={options['players']}",
            f"--symmetry={options['symmetry']}",
            f"--resources={options['resources']}",
            f"--buildings={options['buildings']}",
            f"--density={options['density']}",
            f"--civilian-density={options['civilian-density']}",
            f"--roads={options['roads']}",
            f"--deny-walled-areas={options['deny-walled-areas']}",
            f"--attempts={options['attempts']}",
            f"--title={selection.title}",
        ]
        environment = os.environ.copy()
        environment["ENGINE_DIR"] = str(self.engine_root)
        environment.setdefault("DOTNET_ROLL_FORWARD", "Major")
        completed = subprocess.run(
            command,
            cwd=self.engine_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-2000:]
            raise RuntimeError(f"OpenRA native map generation failed: {detail}")

        metadata: dict[str, Any] | None = None
        for line in reversed(completed.stdout.splitlines()):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and candidate.get("engine_generator") == "classic":
                metadata = candidate
                break
        if not metadata or not metadata.get("ok") or not package_path.is_file():
            raise RuntimeError("OpenRA native map generator did not return a valid result")
        if not metadata.get("passability", {}).get("valid"):
            raise RuntimeError("OpenRA rejected the generated map as impassable for tracked units")

        return NativeMapResult(package_path, metadata, options)
