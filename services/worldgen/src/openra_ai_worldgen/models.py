from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GeoSelection:
    latitude: float
    longitude: float
    title: str = "Earth Skirmish"
    location_name: str = "Selected Earth location"
    radius_m: int = 500
    map_size: int = 64
    seed: int = 1
    source: str = "openstreetmap"
    story_seed: str = ""
    generation_mode: str = "playability-first"
    imagery_style: str = "auto"
    scenario_id: str = ""
    player_faction: str = "random"
    opponent_faction: str = "random"
    mission_archetype: str = "balanced-skirmish"

    def validated(self) -> "GeoSelection":
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if self.map_size not in (64, 96, 128):
            raise ValueError("map_size must be 64, 96, or 128")
        if not 500 <= self.radius_m <= 20000:
            raise ValueError("radius_m must be between 500 and 20000")
        if not 0 <= self.seed <= 2_147_483_647:
            raise ValueError("seed must be between 0 and 2147483647")
        if self.generation_mode not in {"reality-first", "playability-first", "creative-remix"}:
            raise ValueError("generation_mode must be reality-first, playability-first, or creative-remix")
        if self.imagery_style not in {"auto", "hybrid", "satellite", "terrain"}:
            raise ValueError("imagery_style must be auto, hybrid, satellite, or terrain")
        if self.mission_archetype not in {
            "balanced-skirmish",
            "river-crossing",
            "urban-siege",
            "supply-raid",
            "convoy-defense",
            "infrastructure-defense",
        }:
            raise ValueError("mission_archetype is not supported")
        if self.scenario_id:
            from .scenarios import FACTIONS, mission_blueprint

            blueprint = mission_blueprint(self.scenario_id)
            if blueprint is None:
                raise ValueError(f"unknown scenario_id: {self.scenario_id}")
            if self.player_faction not in {"random", *FACTIONS}:
                raise ValueError(f"unknown player_faction: {self.player_faction}")
            if self.opponent_faction not in {"random", *FACTIONS}:
                raise ValueError(f"unknown opponent_faction: {self.opponent_faction}")
            if self.player_faction not in {"random", blueprint.player_faction}:
                raise ValueError("player_faction conflicts with the selected scenario")
            if self.opponent_faction not in {"random", blueprint.opponent_faction}:
                raise ValueError("opponent_faction conflicts with the selected scenario")
        return self

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TerrainAnalysis:
    biome: str = "temperate"
    relief: str = "flat"
    vegetation_density: float = 0.2
    urban_density: float = 0.1
    water_confidence: float = 0.0
    fidelity_notes: tuple[str, ...] = ()
    summary: str = "Terrain translated from available geographic evidence."
    confidence: float = 0.0
    vision_used: bool = False
    model: str = "deterministic"
    latency_ms: int = 0

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TerrainAnalysis":
        def density(name: str, default: float) -> float:
            return max(0.0, min(1.0, float(value.get(name, default))))

        biome = str(value.get("biome", "temperate")).lower()
        relief = str(value.get("relief", "flat")).lower()
        return cls(
            biome=biome if biome in {"desert", "temperate", "snow"} else "temperate",
            relief=relief if relief in {"flat", "rolling", "mountainous"} else "flat",
            vegetation_density=density("vegetation_density", 0.2),
            urban_density=density("urban_density", 0.1),
            water_confidence=density("water_confidence", 0.0),
            fidelity_notes=tuple(str(note)[:120] for note in value.get("fidelity_notes", [])[:3]),
            summary=str(value.get("summary", cls.summary))[:240],
            confidence=density("confidence", 0.0),
            vision_used=bool(value.get("vision_used", False)),
            model=str(value.get("model", "deterministic"))[:160],
            latency_ms=max(0, int(value.get("latency_ms", 0))),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationReport:
    valid: bool
    checks: dict[str, bool]
    metrics: dict[str, int | float | str]
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MissionResult:
    package_path: Path
    preview_path: Path
    manifest_path: Path
    validation: ValidationReport
    source_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "package_path": str(self.package_path),
            "preview_path": str(self.preview_path),
            "manifest_path": str(self.manifest_path),
            "validation": self.validation.as_dict(),
            "source_status": self.source_status,
        }
