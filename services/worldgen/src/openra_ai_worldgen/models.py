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
    radius_m: int = 3500
    map_size: int = 64
    seed: int = 1
    source: str = "openstreetmap"
    story_seed: str = ""

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
        return self

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
