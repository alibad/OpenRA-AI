#!/usr/bin/env python3
"""Validate every built-in RA2 pack/AI combination with private settings."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def check(resources, binaries, content, output, selected):
    name = "-".join(selected) or "classic"
    profile = Path(tempfile.mkdtemp(prefix=name + "-", dir=output))
    (profile / "Content").symlink_to(content, target_is_directory=True)
    settings = "Experience@ra2:\n\tUseCustomComponents: true\n\tEnabledComponents: " + ", ".join(selected) + "\n"
    (profile / "settings.yaml").write_text(settings)
    env = {**os.environ, "ENGINE_DIR": str(resources), "SUPPORT_DIR": str(profile)}
    env.pop("OPENRA_UTILITY_EXPERIENCE_PROFILE", None)
    result = {"selected": selected, "profile": str(profile), "passed": False}

    def utility(*args):
        process = subprocess.run(["dotnet", str(binaries / "OpenRA.Utility.dll"), "ra2", *args],
            cwd=binaries, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
        (profile / (args[0].removeprefix("--") + ("-" + args[1] if args[0] == "--resolved-rules" else "") + ".log")).write_text(process.stdout)
        if process.returncode:
            raise RuntimeError(f"{args}: exit {process.returncode}: {process.stdout[-3000:]}")
        return process.stdout

    try:
        world = utility("--resolved-rules", "World")
        for country in ("china", "iran", "turkey"):
            present = re.search(r"(?m)^Faction@" + country + r":$", world) is not None
            if present != ("ra2-" + country in selected):
                raise ValueError("Faction selection mismatch: " + country)
        for country in ("america", "england", "france", "germany", "korea", "russia", "iraq", "cuba", "libya"):
            if not re.search(r"(?m)^\tInternalName: " + country + r"$", world):
                raise ValueError("Original country missing: " + country)
        player = utility("--resolved-rules", "Player")
        if ("RoleShares:" in player) != ("ra2-combined-arms-ai" in selected):
            raise ValueError("Doctrine AI selection mismatch")
        for kind in ("AdditionalAirUnitsTypes", "AdditionalNavalUnitsTypes", "AdditionalDefenseTypes"):
            for country in ("china", "iran", "turkey"):
                entries = re.findall(r"(?m)^\t" + kind + r":\n((?:\t\t[^\n]*\n)+)", player)
                count = sum(bool(re.search(r"(?m)^\t\t" + country + r":", entry)) for entry in entries)
                expected = 5 if "ra2-" + country in selected else 0
                if count != expected:
                    raise ValueError(f"{kind}/{country}: {count} != {expected}")
        lint = utility("--check-yaml", "mods/ra2/maps/blank-shellmap")
        if "Testing map: Blank" not in lint:
            raise ValueError("Requested map was not actually linted")
        if (profile / "settings.yaml").read_text() != settings:
            raise ValueError("Read-only validation changed saved selections")
        result.update(passed=True, original_countries=9)
    except Exception as exc:
        result["error"] = str(exc)
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("resources", "binaries", "content", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    roots = [getattr(args, key).resolve() for key in ("resources", "binaries", "content", "output")]
    roots[-1].mkdir(parents=True, exist_ok=True)
    components = ("ra2-china", "ra2-iran", "ra2-turkey", "ra2-combined-arms-ai")
    selections = [list(selected) for size in range(5) for selected in itertools.combinations(components, size)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda selected: check(*roots, selected), selections))
    (roots[-1] / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    raise SystemExit(0 if all(row["passed"] for row in results) else 1)
