#!/usr/bin/env python3
"""Prove installed package layouts resolve the shared faction catalog for the game and the companion.

Builds throwaway Windows (<root>/engine/openra + <root>/catalog) and macOS
(OpenRA AI.app/Contents/Resources == engine dir) layouts. The catalog is staged
exactly as the packagers stage it (content_catalog.py --stage), the engine's mod
data is linked in, and RA2 is the data-only integrated mod prepare-ra2.py builds
into package stages. The engine utility then validates each mode WITHOUT an
explicit catalog path, so it must locate the staged file the same way the
in-game Faction Catalog does; the companion locator is checked with the
PyInstaller executable locations and the launchers' OPENRA_AI_ENGINE_DIR.
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
sys.path.insert(0, str(ROOT / "services" / "companion" / "src"))
from openra_ai_companion.faction_catalog import locate_catalog  # noqa: E402


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load("validate_faction_catalog", "validate-faction-catalog.py")


LINKS: list[Path] = []


def link_directory(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    LINKS.append(link)
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def stage_catalog(engine: Path, destination: Path) -> Path:
    subprocess.run([sys.executable, str(ROOT / "scripts/content_catalog.py"), "--engine", str(engine), "--stage", str(destination)],
                   check=True, stdout=subprocess.DEVNULL)
    return destination / "catalog" / "factions.json"


def populate_engine_dir(engine_dir: Path, engine: Path, ra2_mods: Path) -> None:
    for name in ("common", "ra", "ra-content"):
        link_directory(engine_dir / "mods" / name, engine / "mods" / name)
    link_directory(engine_dir / "mods" / "ra2", ra2_mods / "ra2")
    link_directory(engine_dir / "glsl", engine / "glsl")
    for name in ("VERSION", "global mix database.dat"):
        if (engine / name).is_file():
            shutil.copy2(engine / name, engine_dir / name)


def run_utility(engine: Path, engine_dir: Path, mode: str, profile: str, output: Path) -> dict:
    report = output / f"{mode}-report.json"
    with tempfile.TemporaryDirectory(prefix="catalog-layout-") as support:
        env = validator.mode_environment(engine_dir, Path(support), profile, None)
        process = subprocess.run(validator.utility_command(engine) + [mode, "--check-faction-catalog", "--report", str(report)],
                                 cwd=engine_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace", timeout=300)
    (output / f"{mode}.log").write_text(process.stdout, encoding="utf-8")
    data = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}
    return {"exit_code": process.returncode, "valid": data.get("valid"), "catalog": data.get("catalog"),
            "factions": len(data.get("factions", []))}


def launch_game(engine: Path, engine_dir: Path, staged: Path, content: Path, workspace: Path, output: Path) -> dict:
    """Render the in-game catalog from the staged layout with a marked copy of the staged catalog."""
    marker = "Staged package catalog"
    data = json.loads(staged.read_text(encoding="utf-8"))
    next(f for f in data["factions"] if f["id"] == "china")["tagline"] = marker
    staged.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    support = workspace / "support"
    link_directory(support / "Content", content)
    (support / "settings.yaml").write_text(
        "Game:\n\tIntroductionPromptVersion: 2\n\tFetchNews: False\nDebug:\n\tSystemInformationVersionPrompt: 6\n"
        "\tCheckVersion: False\nGraphics:\n\tMode: Windowed\n\tWindowedSize: 1280,720\nSound:\n\tMute: True\n")
    env = {key: value for key, value in os.environ.items() if key not in {"OPENRA_AI_CATALOG", "OPENRA_AI_ROOT"}}
    env.update(OPENRA_DISPLAY_SCALE="1", OPENRA_AI_DISABLE_AUTOSTART="1", OPENRA_AI_START_FACTION_CATALOG="1",
               OPENRA_AI_CAPTURE_FACTION_CATALOG="china", OPENRA_AI_CAPTURE_FACTION_CATALOG_EXIT="1")
    command = ["dotnet", str(engine / "bin" / "OpenRA.dll"), f"Engine.EngineDir={engine_dir}", f"Engine.SupportDir={support}",
               "Game.Mod=ra", "Game.Platform=Default"]
    try:
        process = subprocess.run(command, cwd=engine / "bin", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace", timeout=240)
        exit_code = process.returncode
    except subprocess.TimeoutExpired:
        exit_code = "timeout"
    screenshots = sorted((support / "Screenshots").rglob("*.png"))
    saved = []
    for index, shot in enumerate(screenshots):
        target = output / f"packaged-layout-catalog-{index}.png"
        shutil.copy2(shot, target)
        saved.append(str(target))
    log = support / "Logs" / "debug.log"
    captured = log.is_file() and "Faction catalog capture 0: china -> china/" in log.read_text(encoding="utf-8", errors="replace")
    return {"exit_code": exit_code, "screenshots": saved, "marker": marker, "passed": exit_code == 0 and bool(saved) and captured}


def same_path(a: str | Path | None, b: Path) -> bool:
    return a is not None and os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=ROOT.parent / "OpenRA")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "catalog-package-layout")
    parser.add_argument("--launch-game", action="store_true",
                        help="Also open the Faction Catalog from the staged Windows layout and save a native screenshot")
    parser.add_argument("--content", type=Path, default=ROOT.parent / "OpenRA" / "Support" / "Content",
                        help="Existing game content, linked read-only into a disposable profile for --launch-game")
    args = parser.parse_args(argv)
    engine = args.engine.resolve()
    if not validator.supports_catalog_check(engine):
        raise SystemExit(f"{engine} has no built Faction Catalog support")

    catalog = json.loads((ROOT / "catalog/factions.json").read_text(encoding="utf-8"))
    profiles = {mode: validator.profile_for(catalog, mode) for mode in ("ra", "ra2")}
    args.output.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="layout-", dir=args.output))
    results: dict[str, dict] = {}
    try:
        ra2_mods = validator.prepare_ra2_mods(engine, workspace / "ra2")
        layouts = {
            "windows": (workspace / "OpenRA-AI-windows-x64", Path("engine/openra"), Path("bin/openra-ai-companion.exe")),
            "macos": (workspace / "OpenRA AI.app/Contents/Resources", Path("."), Path("bin/openra-ai-companion")),
        }
        for name, (root, engine_relative, companion_relative) in layouts.items():
            staged = stage_catalog(engine, root)
            engine_dir = (root / engine_relative).resolve()
            populate_engine_dir(engine_dir, engine, ra2_mods)
            output = args.output / name
            output.mkdir(parents=True, exist_ok=True)
            game = {mode: run_utility(engine, engine_dir, mode, profiles[mode], output) for mode in ("ra", "ra2")}
            # PyInstaller onefile unpacks modules elsewhere; only the executable path identifies the install.
            unpacked = str(workspace / "_MEI" / "openra_ai_companion" / "faction_catalog.py")
            companion = {
                "frozen_executable": str(locate_catalog(env={}, executable=str(root / companion_relative), frozen=True,
                                                        module_file=unpacked)),
                "launcher_engine_dir": str(locate_catalog(env={"OPENRA_AI_ENGINE_DIR": str(engine_dir)}, frozen=False,
                                                          module_file=unpacked)),
            }
            passed = all(r["exit_code"] == 0 and r["valid"] and same_path(r["catalog"], staged) for r in game.values()) and \
                all(same_path(path, staged) for path in companion.values())
            results[name] = {"staged_catalog": str(staged), "engine_dir": str(engine_dir), "game": game,
                             "companion": companion, "passed": passed}
            if args.launch_game and name == "windows":
                results[name]["rendered"] = launch_game(engine, engine_dir, staged, args.content.resolve(), workspace, output)
                results[name]["passed"] &= results[name]["rendered"]["passed"]
    finally:
        # Remove the links themselves first so cleanup can never reach the linked engine checkout.
        for link in reversed(LINKS):
            if os.name == "nt":
                os.rmdir(link)
            else:
                link.unlink()
        shutil.rmtree(workspace, ignore_errors=True)

    summary = {"engine": str(engine), "passed": all(r["passed"] for r in results.values()), "layouts": results}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
