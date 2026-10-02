#!/usr/bin/env python3
"""Geometry lint for the fixed-camera faction sprite meshes.

The shared renderer in ``red_sea_directional_vehicle._render`` draws a face
only when its normal points toward the camera.  Two authoring mistakes make
geometry silently disappear from every facing:

* an open, single-sided panel (a wing, tailplane or deck plate authored as one
  polygon) whose vertex winding makes its normal point downward, and
* a closed shell in which neighbouring faces wind a shared edge in the same
  direction, so part of the shell faces inward and is culled (the hull renders
  as an open frame).

This lint inspects every mesh builder used by the China, Iran, Red Sea and
Turkey sprite generators.  It is a companion to
``modern_faction_art_audit.py``, which measures the rendered consequences
(missing planforms and see-through silhouettes) in the shipped SHP files.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# (module, function, kwargs) for every mesh builder feeding a shipped sprite.
MESH_BUILDERS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("red_sea_directional_vehicle", "_m1_hull", {}),
    ("red_sea_directional_vehicle", "_m1_turret", {}),
    ("red_sea_directional_vehicle", "_sads_hull", {}),
    ("red_sea_directional_vehicle", "_sads_turret", {}),
    ("red_sea_directional_vehicle", "_tech_hull", {}),
    ("red_sea_directional_vehicle", "_tech_turret", {}),
    ("red_sea_directional_vehicle", "_ymlr_hull", {"loaded": True}),
    ("red_sea_directional_vehicle", "_ymlr_hull", {"loaded": False}),
    ("red_sea_directional_vehicle", "_samad_airframe", {}),
    ("red_sea_directional_vehicle", "_f15sa_airframe", {}),
    ("red_sea_directional_vehicle", "_ah64sa_airframe", {}),
    ("iran_directional_assets", "_karrar_hull", {}),
    ("iran_directional_assets", "_karrar_turret", {}),
    ("iran_directional_assets", "_truck_hull", {}),
    ("iran_directional_assets", "_raad_turret", {}),
    ("iran_directional_assets", "_fajr_turret", {"loaded": True}),
    ("iran_directional_assets", "_fajr_turret", {"loaded": False}),
    ("iran_directional_assets", "_coast_turret", {}),
    ("iran_directional_assets", "_azar_airframe", {}),
    ("iran_directional_assets", "_toufan_airframe", {}),
    ("iran_directional_assets", "_mohajer_airframe", {}),
    ("iran_directional_assets", "_loiter_airframe", {}),
    ("iran_directional_assets", "_peykaap_hull", {}),
    ("iran_directional_assets", "_peykaap_turret", {}),
    ("iran_directional_assets", "_ghadir_hull", {}),
    ("iran_directional_assets", "_classic_peykaap_hull", {}),
    ("iran_directional_assets", "_classic_peykaap_turret", {}),
    ("turkey_directional_assets", "_tracked_hull", {}),
    ("turkey_directional_assets", "_wheeled_hull", {"axles": 4}),
    ("turkey_directional_assets", "_wheeled_hull", {"axles": 4, "amphibious": True}),
    ("turkey_directional_assets", "_wheeled_hull", {"axles": 4, "ew": True}),
    *(("turkey_directional_assets", "_turret", {"kind": kind}) for kind in ("bozkir", "yildirim", "gokkalkan", "sancak", "remote")),
    *(("turkey_directional_assets", "_airframe", {"kind": kind}) for kind in ("kuzgunm", "sahinx", "turnaah")),
    *(("turkey_directional_assets", "_ship_hull", {"kind": kind}) for kind in ("marmara", "ege", "poyraz")),
    *(("turkey_directional_assets", "_ship_turret", {"kind": kind}) for kind in ("marmara", "ege", "poyraz")),
    *(("turkey_directional_assets", "_classic_ship_hull", {"kind": kind}) for kind in ("marmara", "ege", "poyraz")),
    *(("turkey_directional_assets", "_classic_ship_turret", {"kind": kind}) for kind in ("marmara", "ege", "poyraz")),
    ("china_directional_assets", "_qilin_hull", {}),
    ("china_directional_assets", "_qilin_turret", {}),
    ("china_directional_assets", "_lynx_hull", {}),
    ("china_directional_assets", "_lynx_turret", {}),
    ("china_directional_assets", "_mantis_hull", {}),
    ("china_directional_assets", "_mantis_turret", {}),
    ("china_directional_assets", "_zbd_hull", {}),
    ("china_directional_assets", "_zbd_turret", {}),
    ("china_directional_assets", "_phl", {"loaded": True}),
    ("china_directional_assets", "_phl", {"loaded": False}),
    ("china_directional_assets", "_plane_mesh", {"drone": False}),
    ("china_directional_assets", "_plane_mesh", {"drone": True}),
    ("china_directional_assets", "_crane", {}),
    *(("china_directional_assets", "_ship_hull", {"kind": kind}) for kind in ("cnluyang", "cnhaiwang", "cnhaiying", "cnkunlun", "cnjiaolong")),
    *(("china_directional_assets", "_ship_turret", {"kind": kind}) for kind in ("cnluyang", "cnhaiwang", "cnhaiying", "cnkunlun")),
    *(("china_directional_assets", "_defense_base", {"kind": kind}) for kind in ("cnbastion", "cnskyshield", "cnspectrum")),
    *(("china_directional_assets", "_defense_top", {"kind": kind}) for kind in ("cnbastion", "cnskyshield", "cnspectrum")),
)

PRECISION = 4


def _key(vertex) -> tuple[float, float, float]:
    return tuple(round(float(value), PRECISION) for value in vertex)  # type: ignore[return-value]


def lint_mesh(mesh) -> dict[str, Any]:
    """Return hidden open panels and inconsistently wound shared edges."""

    directed: dict[tuple, list[int]] = {}
    for index, face in enumerate(mesh.faces):
        points = [_key(v) for v in face.vertices]
        for a, b in zip(points, points[1:] + points[:1]):
            if a == b:
                continue
            directed.setdefault((a, b), []).append(index)

    def undirected_count(a, b) -> int:
        return len(directed.get((a, b), [])) + len(directed.get((b, a), []))

    hidden_panels = []
    for index, face in enumerate(mesh.faces):
        points = [_key(v) for v in face.vertices]
        edges = [(a, b) for a, b in zip(points, points[1:] + points[:1]) if a != b]
        shared = sum(1 for a, b in edges if undirected_count(a, b) > 1)
        # Every edge unshared: a stand-alone panel. If its normal points
        # down it can never face the elevated camera, whatever the yaw.
        if edges and shared == 0 and face.normal[2] < -0.5:
            hidden_panels.append({"face": index, "normal": [round(n, 3) for n in face.normal], "color": list(face.color)})

    conflicts = []
    for (a, b), faces in directed.items():
        # Only manifold edges (exactly two faces) constrain orientation; an
        # edge shared by three or more faces (a plate touching a closed box)
        # necessarily repeats a direction.
        if len(faces) > 1 and undirected_count(a, b) == 2:
            # Two faces walk the same edge in the same direction: one of them
            # is wound backwards relative to its neighbour.
            conflicts.append({"edge": [list(a), list(b)], "faces": faces})
    return {"faces": len(mesh.faces), "hidden_open_panels": hidden_panels, "winding_conflicts": conflicts}


# Classic-sprite meshes that must be closed, consistently wound shells.
CLOSED_SHELLS = {"_classic_ship_hull"}
# Shared meshes that the classic sprites do not render directly (RA2 voxel
# builders consume them with their own corrections): reported, never gated.
NOT_CLASSIC = {("turkey_directional_assets", "_ship_hull")}


def lint_all(builders=MESH_BUILDERS) -> dict[str, dict[str, Any]]:
    """Lint source meshes and the faces the classic sprite renderer draws."""

    from red_sea_directional_vehicle import Mesh, _classic_faces

    results: dict[str, dict[str, Any]] = {}
    for module_name, function_name, kwargs in builders:
        module = importlib.import_module(module_name)
        builder: Callable = getattr(module, function_name)
        label = f"{module_name}.{function_name}({', '.join(f'{k}={v!r}' for k, v in kwargs.items())})"
        mesh = builder(**kwargs)
        result = lint_mesh(mesh)
        classic = Mesh()
        classic.faces = _classic_faces(mesh)
        classic_result = lint_mesh(classic)
        result["classic_hidden_open_panels"] = classic_result["hidden_open_panels"]
        result["classic_winding_conflicts"] = classic_result["winding_conflicts"]
        result["closed_shell_required"] = function_name in CLOSED_SHELLS
        result["classic"] = (module_name, function_name) not in NOT_CLASSIC
        results[label] = result
    return results


def classic_failures(result: dict[str, Any]) -> list[str]:
    """Defects visible in classic sprites (source-mesh notes are informational)."""

    failures = []
    if not result.get("classic", True):
        return failures
    if result["classic_hidden_open_panels"]:
        failures.append(f"{len(result['classic_hidden_open_panels'])} open panel(s) culled at every facing")
    if result["classic_winding_conflicts"]:
        failures.append(f"{len(result['classic_winding_conflicts'])} shared edge(s) still wound inconsistently")
    if result["closed_shell_required"] and result["winding_conflicts"]:
        failures.append(f"{len(result['winding_conflicts'])} winding conflict(s) in a closed hull")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", type=Path, help="write the full report here")
    args = parser.parse_args(argv)
    results = lint_all()
    failures = 0
    for label, result in results.items():
        problems = classic_failures(result)
        if problems:
            failures += 1
            print(f"FAIL {label}: {'; '.join(problems)}")
        elif result["hidden_open_panels"] or result["winding_conflicts"]:
            print(f"note {label}: source mesh has {len(result['hidden_open_panels'])} downward open panel(s) and "
                  f"{len(result['winding_conflicts'])} winding conflict(s); the classic renderer compensates or they are "
                  "hidden inside closed geometry (RA2 voxel builders apply their own corrections)")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"linted {len(results)} mesh builder(s): {failures} with defects")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
