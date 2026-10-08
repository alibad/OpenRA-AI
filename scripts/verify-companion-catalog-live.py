#!/usr/bin/env python3
"""Live check: the running game shares its rules with the companion, which answers catalog questions per mode.

Starts a private companion API and a headless (Null platform) game for each mode
with disposable settings and ports. The game's main menu posts its rules digest
to the companion; the companion must then answer catalog questions for that
mode from the digest without calling a model, and must not describe factions
that the mode does not implement.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = {
    "ra": [
        ("Which Yemen unit is anti-air?", ["SAM Site", "None of its mobile units"], ["Red Alert 2"]),
        ("What does the Qilin counter?", ["Qilin Main Battle Tank (China, Classic)", "counter armor"], []),
    ],
    "ra2": [
        ("Which Yemen unit is anti-air?", ["isn't available in Red Alert 2"], ["SAM Site"]),
        ("What does the Qilin counter?", ["(China, Red Alert 2)"], ["Classic)"]),
        ("Which Iran unit is anti-air?", ["Raad Air Defense"], []),
    ],
}


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def request(url: str, payload: dict | None = None, timeout: float = 10) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def wait_for(predicate, timeout: float, interval: float = 0.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except (OSError, urllib.error.URLError, ValueError):
            pass
        time.sleep(interval)
    return None


def run_mode(mode: str, engine: Path, content: Path, ra2_mods: Path | None, output: Path, match_map: str | None = None) -> dict:
    workspace = Path(tempfile.mkdtemp(prefix=f"companion-{mode}-", dir=output))
    support = workspace / "support"
    support.mkdir()
    appdata = workspace / "appdata"
    appdata.mkdir()
    link = support / "Content"
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(content), str(link))
    else:
        link.symlink_to(content, target_is_directory=True)
    (support / "settings.yaml").write_text(
        "Game:\n\tIntroductionPromptVersion: 2\n\tFetchNews: False\nDebug:\n\tSystemInformationVersionPrompt: 6\n\tCheckVersion: False\n")

    console, bridge = free_port(), free_port()
    companion_env = {key: value for key, value in os.environ.items() if key not in {"OPENRA_AI_CATALOG", "OPENRA_AI_FACTION_DIGEST_DIR"}}
    companion_env.update(APPDATA=str(appdata), OPENRA_AI_ROUTER_URL=f"http://127.0.0.1:{free_port()}",
                         PYTHONPATH=os.pathsep.join([str(ROOT / "services/companion/src"), str(ROOT / "services/worldgen/src")]))
    game_env = {key: value for key, value in os.environ.items() if key not in {"OPENRA_AI_CATALOG", "OPENRA_AI_ROOT"}}
    game_env.update(OPENRA_AI_COMPANION="1", OPENRA_AI_DISABLE_AUTOSTART="1", OPENRA_AI_GRPC_PORT=str(bridge),
                    OPENRA_AI_CONSOLE_URL=f"http://127.0.0.1:{console}/", OPENRA_AI_CATALOG=str(ROOT / "catalog/factions.json"))
    command = ["dotnet", str(engine / "bin/OpenRA.dll"), f"Engine.EngineDir={engine}", f"Engine.SupportDir={support}",
               f"Game.Mod={mode}", "Game.Platform=Null"]
    if mode == "ra2":
        command.append(f"Engine.ModSearchPaths={engine / 'mods'},{ra2_mods}")

    result: dict = {"mode": mode, "passed": False, "answers": []}
    companion = subprocess.Popen([sys.executable, "-m", "openra_ai_companion.cli", "serve", "--port", str(console)],
                                 cwd=ROOT, env=companion_env, stdout=(workspace / "companion.log").open("w"),
                                 stderr=subprocess.STDOUT)
    game = None
    try:
        base = f"http://127.0.0.1:{console}"
        if not wait_for(lambda: request(base + "/health"), 30):
            raise RuntimeError("companion did not start")
        game = subprocess.Popen(command, cwd=engine / "bin", env=game_env, stdout=(workspace / "game.log").open("w"),
                                stderr=subprocess.STDOUT)
        status = wait_for(lambda: (s := request(base + "/v1/factions")) and mode in s["live_modes"] and s, 120)
        if not status:
            raise RuntimeError("the game did not publish its rules digest")
        result["live"] = status["live_modes"][mode]
        passed = result["live"]["source"] == "main-menu"
        for question, expected, forbidden in QUESTIONS[mode]:
            answer = request(base + "/v1/ask", {"question": question}, timeout=30)
            ok = answer["source"] == "faction-catalog" and all(e in answer["text"] for e in expected) and \
                not any(f in answer["text"] for f in forbidden)
            result["answers"].append({"question": question, "source": answer["source"], "text": answer["text"], "passed": ok})
            passed &= ok
        if match_map:
            # A match republishes its own map rules from the companion HUD.
            game.terminate()
            game.wait(timeout=15)
            game = subprocess.Popen(command + [f"Launch.Map={match_map}", "Launch.Bots=Multi1:normal"], cwd=engine / "bin",
                                    env=game_env, stdout=(workspace / "match.log").open("w"), stderr=subprocess.STDOUT)
            match = wait_for(lambda: (s := request(base + "/v1/factions")) and s["live_modes"].get(mode, {}).get("source") == "match" and s, 180)
            result["match"] = match["live_modes"][mode] if match else None
            passed &= match is not None
        result["passed"] = passed
    except Exception as exc:  # recorded in the summary; processes are always stopped below
        result["error"] = str(exc)
    finally:
        for process in (game, companion):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()
        result["logs"] = str(workspace)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=ROOT.parent / "OpenRA")
    parser.add_argument("--content", type=Path, default=ROOT.parent / "OpenRA" / "Support" / "Content")
    parser.add_argument("--ra2-mods", type=Path, help="Integrated mods directory containing ra2/ (prepared when omitted)")
    parser.add_argument("--modes", nargs="+", choices=("ra", "ra2"), default=["ra", "ra2"])
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "companion-catalog-live")
    parser.add_argument("--classic-match", default="a-nuclear-winter", help="Classic map to start for the in-match check (empty to skip)")
    args = parser.parse_args(argv)
    engine, content = args.engine.resolve(), args.content.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    ra2_mods = args.ra2_mods.resolve() if args.ra2_mods else None
    prepared = None
    if "ra2" in args.modes and ra2_mods is None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("validate_faction_catalog", ROOT / "scripts/validate-faction-catalog.py")
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        prepared = Path(tempfile.mkdtemp(prefix="ra2-", dir=args.output))
        ra2_mods = validator.prepare_ra2_mods(engine, prepared)
    try:
        results = [run_mode(mode, engine, content, ra2_mods, args.output, args.classic_match if mode == "ra" else None)
                   for mode in args.modes]
    finally:
        if prepared is not None:
            shutil.rmtree(prepared, ignore_errors=True)
    summary = {"engine": str(engine), "passed": all(r["passed"] for r in results), "modes": results}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
