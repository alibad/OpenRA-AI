#!/usr/bin/env python3
"""Check the shared faction catalog against each game mode's loaded engine rules.

For Classic (`ra`) and Red Alert 2 (`ra2`) this runs the engine's
`--check-faction-catalog` utility with that mode's catalog profile. It fails when
a catalog unit's actor is missing from the mode's rules or not buildable by its
faction, a faction pack or a buildable faction-exclusive actor is missing from
the catalog, a unit leaks into a mode where its faction is unavailable, or a
deep link to the public site is malformed. RA2 is checked against a data-only
integrated RA2 mod prepared from the pinned upstream source (no game content).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


content_catalog = _load("content_catalog", "content_catalog.py")


def profile_for(catalog: dict, mode: str) -> str:
    matches = [profile["id"] for profile in catalog["profiles"] if profile["mode"] == mode]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one catalog profile for {mode}, found {matches}")
    return matches[0]


def utility_command(engine: Path) -> list[str]:
    dll = engine / "bin" / "OpenRA.Utility.dll"
    if not dll.is_file():
        raise FileNotFoundError(f"Build the engine first: {dll} is missing")
    return ["dotnet", str(dll)]


def supports_catalog_check(engine: Path) -> bool:
    return (engine / "mods/common/chrome/faction-catalog.yaml").is_file() and (engine / "bin/OpenRA.Utility.dll").is_file()


def mode_environment(engine: Path, support: Path, profile: str, ra2_mods: Path | None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if key not in {"OPENRA_AI_CATALOG", "OPENRA_AI_ROOT", "MOD_SEARCH_PATHS"}}
    env.update(ENGINE_DIR=str(engine), SUPPORT_DIR=str(support), OPENRA_UTILITY_EXPERIENCE_PROFILE=profile)
    if ra2_mods is not None:
        env["MOD_SEARCH_PATHS"] = ",".join((str(engine / "mods"), str(ra2_mods)))
    return env


def prepare_ra2_mods(engine: Path, workspace: Path) -> Path:
    """Data-only integrated RA2 mod for validation. Uses the pinned, checksum-verified source archive."""
    prepare = _load("prepare_ra2", "prepare-ra2.py")
    stage = workspace / "ra2-stage"
    binaries = workspace / "ra2-binaries"
    binaries.mkdir(parents=True, exist_ok=True)
    prepare.prepare(stage, binaries, "{DEV_VERSION}", True, "win-x64", engine, True)
    return stage / "mods"


def check_mode(engine: Path, catalog_path: Path, mode: str, output: Path, ra2_mods: Path | None = None) -> dict:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    profile = profile_for(catalog, mode)
    output.mkdir(parents=True, exist_ok=True)
    report_path, digest_path = output / f"{mode}-report.json", output / f"{mode}-digest.json"
    with tempfile.TemporaryDirectory(prefix=f"catalog-{mode}-") as support:
        env = mode_environment(engine, Path(support), profile, ra2_mods if mode == "ra2" else None)
        command = utility_command(engine) + [mode, "--check-faction-catalog", str(catalog_path),
                                             "--report", str(report_path), "--digest", str(digest_path)]
        process = subprocess.run(command, cwd=engine, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace", timeout=300)
    (output / f"{mode}.log").write_text(process.stdout, encoding="utf-8")
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    return {
        "mode": mode,
        "profile": profile,
        "exit_code": process.returncode,
        "valid": process.returncode == 0 and report.get("valid") is True,
        "factions": [f"{f['kind']}:{f['key']}" for f in report.get("factions", [])],
        "issues": report.get("issues", []) or [line for line in process.stdout.splitlines() if line.startswith("Error")],
        "report": str(report_path),
        "digest": str(digest_path) if digest_path.is_file() else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=ROOT.parent / "OpenRA", help="Built engine checkout")
    parser.add_argument("--catalog", type=Path, default=content_catalog.CATALOG)
    parser.add_argument("--modes", nargs="+", choices=("ra", "ra2"), default=["ra", "ra2"])
    parser.add_argument("--ra2-mods", type=Path, help="Existing integrated mods directory containing ra2/")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "faction-catalog-validation")
    args = parser.parse_args(argv)

    engine = args.engine.resolve()
    catalog_path = args.catalog.resolve()
    content_catalog.validate(json.loads(catalog_path.read_text(encoding="utf-8")), engine)
    if not supports_catalog_check(engine):
        raise SystemExit(f"{engine} has no built Faction Catalog support (mods/common/chrome/faction-catalog.yaml, bin/OpenRA.Utility.dll)")

    args.output.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="ra2-", dir=args.output))
    try:
        ra2_mods = args.ra2_mods.resolve() if args.ra2_mods else None
        if "ra2" in args.modes and ra2_mods is None:
            ra2_mods = prepare_ra2_mods(engine, workspace)
        results = [check_mode(engine, catalog_path, mode, args.output, ra2_mods) for mode in args.modes]
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    summary = {"catalog": str(catalog_path), "engine": str(engine), "valid": all(r["valid"] for r in results), "modes": results}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
