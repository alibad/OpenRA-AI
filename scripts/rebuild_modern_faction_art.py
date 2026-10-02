#!/usr/bin/env python3
"""Regenerate the non-infantry Classic modern-faction sprites into an engine.

The per-faction ``build-*-assets.ps1`` scripts also rebuild sound effects,
voices, missions and the raw infantry sheets.  Custom infantry world art and
most infantry cameos are now re-authored by the engine's
``packaging/artwork/generate_faction_infantry_art.py``, so blindly rerunning
those scripts would overwrite the shipped infantry with the older raw frames.

This driver runs only the deterministic sprite generators, converts the
vehicle, aircraft, ship, defense, effect and non-infantry icon frames to SHP
with the engine's own ``OpenRA.Utility --shp`` and reports every package whose
bytes change.  ``--check`` compares without writing, which proves the
generators reproduce the shipped art before a fix is made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

FACTIONS: dict[str, dict[str, object]] = {
    "china": {
        "script": "build-china-assets.py",
        "staging": "china-faction-sprites",
        "assets": (
            "cnqilin", "cnqilinhusk", "cnlynx", "cnlynxhusk", "cnzbd", "cnzbdhusk", "cnphl", "cnphlhusk", "cnmantis", "cnmantishusk",
            "cnskyspear", "cnskyspearhusk", "cncloud", "cncloudhusk", "cncrane", "cncranehusk", "cncranerotor",
            "cnluyang", "cnluyangturret", "cnluyangsink", "cnhaiwang", "cnhaiwangturret", "cnhaiwangsink",
            "cnhaiying", "cnhaiyingturret", "cnhaiyingsink", "cnkunlun", "cnkunlunturret", "cnkunlunsink", "cnjiaolong", "cnjiaolongsink",
            "cnbastion", "cnbastiontop", "cnskyshield", "cnskyshieldtop", "cnspectrum", "cnspectrumtop",
            "china-heavy-muzzle", "china-light-muzzle", "china-missile", "china-drone-projectile",
            "china-network-pulse", "china-network-impact", "china-precision-impact", "china-naval-impact", "china-wake",
            "cnqilinicon", "cnlynxicon", "cnzbdicon", "cnphlicon", "cnskyspearicon", "cncloudicon", "cncraneicon",
            "cnluyangicon", "cnhaiwangicon", "cnmantisicon", "cnhaiyingicon", "cnkunlunicon", "cnjiaolongicon",
            "cnbastionicon", "cnskyshieldicon", "cnspectrumicon",
        ),
    },
    "iran": {
        "script": "build-iran-sprites.py",
        "staging": "iran-sprites",
        "assets": (
            "irkarr", "irraad", "irfajr", "ircoast",
            "irazar", "irtoufan", "irmohajer", "irloiter", "irpey", "irghadir",
            "irkarrhusk", "irraadhusk", "irfajrhusk", "ircoasthusk",
            "irazarhusk", "irtoufanhusk", "irmohajerhusk", "irpeysink", "irghadirsink",
            "irtoufanrotor", "irmuzzle", "irimpact", "irsabotage", "ircloak", "irwake", "irmissile",
            "irkarricon", "irraadicon", "irfajricon", "ircoasticon",
            "irazaricon", "irtoufanicon", "irmohajericon", "irloitericon", "irpeyicon", "irghadiricon",
        ),
    },
    "red-sea": {
        "script": "build-red-sea-sprites.py",
        "staging": "red-sea-sprites",
        "assets": (
            "m1a2s", "sads", "tech", "ymlr", "samad", "f15sa", "ah64sa",
            "m1a2shusk", "sadshusk", "techhusk", "ymlrhusk", "samadhusk", "f15sahusk", "ah64sahusk",
            "m1a2sicon", "sadsicon", "techicon", "ymlricon", "samadicon", "f15saicon", "ah64saicon",
            "ah64sarotor", "redsea-m1-impact", "redsea-m1-muzzle", "redsea-drone-impact",
            "redsea-air-muzzle", "redsea-air-impact",
        ),
    },
    "turkey": {
        "script": "build-turkey-sprites.py",
        "staging": "turkey-sprites",
        "assets": (
            "bozkir", "bozkirhusk", "aras8", "aras8husk", "yildirim", "yildirimhusk",
            "gokkalkan", "gokkalkanhusk", "sancak", "sancakhusk", "denizkaplan", "denizkaplanhusk",
            "kuzgunm", "kuzgunmhusk", "turnaah", "turnaahhusk", "sahinx", "sahinxhusk",
            "marmara", "marmarasink", "ege", "egesink", "poyraz", "poyrazsink",
            "bozkiricon", "aras8icon", "yildirimicon", "gokkalkanicon", "sancakicon", "denizkaplanicon",
            "kuzgunmicon", "turnaahicon", "sahinxicon", "marmaraicon", "egeicon", "poyrazicon", "turnaahrotor",
            "turkey-ground-muzzle", "turkey-air-muzzle", "turkey-designator", "turkey-wake",
            "turkey-at-impact", "turkey-heavy-impact", "turkey-artillery-impact", "turkey-air-impact", "turkey-naval-impact",
        ),
    },
}


def utility_env(engine: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["ENGINE_DIR"] = str(engine)
    env["DOTNET_ROLL_FORWARD"] = "Major"
    return env


def utility(engine: Path) -> Path:
    return engine / "bin" / ("OpenRA.Utility.exe" if os.name == "nt" else "OpenRA.Utility")


def palette_reference(engine: Path, work: Path) -> Path:
    """Export the native 2TNK frame 0 with the RA palette, exactly like the build scripts."""

    folder = work / "palette"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    palette = engine / "mods" / "ra" / "maps" / "chernobyl" / "temperat.pal"
    env = utility_env(engine)
    for args in (["--extract", "2tnk.shp"], ["--png", "2tnk.shp", str(palette), "--noshadow"]):
        subprocess.run([str(utility(engine)), "ra", *args], cwd=folder, env=env, check=True, capture_output=True)
    frames = sorted(folder.glob("2tnk-*.png"))
    if not frames:
        raise RuntimeError("palette export produced no frames")
    return frames[0]


def pack(engine: Path, directory: Path, asset: str) -> Path:
    for stale in directory.glob("*.shp"):
        stale.unlink()
    frames = sorted(directory.glob(f"{asset}-[0-9][0-9][0-9][0-9].png"))
    if not frames:
        raise RuntimeError(f"no frames for {asset} in {directory}")
    subprocess.run([str(utility(engine)), "ra", "--shp", *(frame.name for frame in frames)], cwd=directory,
                   env=utility_env(engine), check=True, capture_output=True)
    packages = sorted(directory.glob("*.shp"))
    if len(packages) != 1:
        raise RuntimeError(f"expected one SHP for {asset}, found {packages}")
    return packages[0]


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--engine", type=Path, default=ROOT / "engine" / "openra")
    parser.add_argument("--factions", nargs="+", default=list(FACTIONS), choices=list(FACTIONS))
    parser.add_argument("--check", action="store_true", help="report differences without writing into the engine")
    parser.add_argument("--report", type=Path, help="write a JSON change report")
    parser.add_argument("--skip-generate", action="store_true", help="reuse frames already generated")
    args = parser.parse_args(argv)

    engine = args.engine.resolve()
    bits = engine / "mods" / "ra" / "bits"
    generated = ROOT / "generated"
    report: dict[str, dict[str, object]] = {}
    reference = palette_reference(engine, generated / "modern-faction-rebuild")
    for faction in args.factions:
        spec = FACTIONS[faction]
        if not args.skip_generate:
            subprocess.run([PYTHON, str(ROOT / "scripts" / str(spec["script"])), "--palette", str(reference)],
                           cwd=ROOT, check=True)
        staging = generated / str(spec["staging"])
        changes: dict[str, object] = {}
        for asset in spec["assets"]:  # type: ignore[union-attr]
            package = pack(engine, staging / asset, asset)
            target = bits / f"{asset}.shp"
            before, after = digest(target), digest(package)
            if before != after:
                changes[asset] = {"before": before, "after": after}
                if not args.check:
                    shutil.copyfile(package, target)
        report[faction] = {"assets": len(spec["assets"]), "changed": changes}  # type: ignore[arg-type]
        print(f"{faction}: {len(changes)} of {len(spec['assets'])} package(s) differ from the engine")  # type: ignore[arg-type]
        for asset in changes:
            print(f"  {asset}")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
