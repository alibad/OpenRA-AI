from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
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


def generation_options(selection: GeoSelection, analysis: TerrainAnalysis) -> dict[str, str | int | bool]:
    if analysis.urban_density >= 0.55:
        civilian_density = "High"
    elif analysis.urban_density >= 0.25:
        civilian_density = "Medium"
    elif analysis.urban_density >= 0.10:
        civilian_density = "Low"
    else:
        civilian_density = "None"

    return {
        "tileset": {"desert": "DESERT", "snow": "SNOW"}.get(analysis.biome, "TEMPERAT"),
        "size": selection.map_size,
        "seed": selection.seed,
        "terrain": terrain_profile(analysis),
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
        windows = self.engine_root / "bin" / "OpenRA.Utility.exe"
        return windows if windows.is_file() else self.engine_root / "bin" / "OpenRA.Utility"

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
