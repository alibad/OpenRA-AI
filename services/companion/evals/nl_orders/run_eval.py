"""Run the natural-language order evaluation with one command.

    # Start the shipping local model (checksum-pinned pack in ./ai), evaluate, stop it:
    python services/companion/evals/nl_orders/run_eval.py --start-local-ai

    # Evaluate against an already running OpenAI-compatible router:
    python services/companion/evals/nl_orders/run_eval.py --router-url http://127.0.0.1:4000

    # Deterministic-only smoke run (no model; model calls fail softly):
    python services/companion/evals/nl_orders/run_eval.py --offline

``--src`` evaluates another companion source tree (for example a ``git archive``
of the previous release) with exactly the same cases, fixtures and grader.
``--mode live`` also attaches the interactive MCP planner used by
``openra-ai-companion watch``, backed by a read-only replay of each fixture.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[3]
DEFAULT_SRC = REPOSITORY / "services" / "companion" / "src"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_http(url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"{url} did not become ready")


def start_local_ai(ai_root: Path, profile_id: str, log: Path) -> tuple[subprocess.Popen, str]:
    """Start the product's local runtime gateway exactly as the launcher does."""
    lock = json.loads((REPOSITORY / "packaging" / "ai-pack.lock.json").read_text(encoding="utf-8"))
    profile = next(item for item in lock["model_profiles"] if item["id"] == profile_id)
    gateway, chat, stt = _free_port(), _free_port(), _free_port()
    environment = {**os.environ, "OPENRA_AI_LOCAL_CHAT_PORT": str(chat), "OPENRA_AI_LOCAL_TRANSCRIBE_PORT": str(stt)}
    environment["PYTHONPATH"] = str(DEFAULT_SRC) + os.pathsep + environment.get("PYTHONPATH", "")
    log.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [sys.executable, "-m", "openra_ai_companion.local_runtime", "serve", "--root", str(ai_root), "--mode", "local",
         "--port", str(gateway), "--model-profile", json.dumps(profile)],
        env=environment, stdout=log.open("wb"), stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    url = f"http://127.0.0.1:{gateway}"
    try:
        _wait_http(url + "/health/liveliness", 240)
    except Exception:
        process.terminate()
        raise
    return process, url


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()


# ---------------------------------------------------------------------------
# Worker (runs with PYTHONPATH pointing at the companion source under test)
# ---------------------------------------------------------------------------

def _jsonable(value):
    return json.loads(json.dumps(value, default=str))


def worker(args: argparse.Namespace) -> int:
    from openra_ai_companion.core import Companion
    from openra_ai_companion.models import GameSnapshot
    from openra_ai_companion.router import AIRouter, RouterError, RouterResult
    from openra_ai_companion.settings import Settings

    sys.path.insert(0, str(HERE))
    from cases import cases as load_cases

    selected = {line.strip() for line in Path(args.case_file).read_text(encoding="utf-8").splitlines() if line.strip()}
    output = Path(args.outcomes)
    done = set()
    if output.is_file():
        for line in output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["id"])
    settings = Settings(
        router_url=args.router_url,
        model_provider="local" if not args.external else "custom",
        text_model=args.model,
        vision_model="local-no-vision" if args.profile == "lightweight" else args.model,
        timeout_seconds=float(args.timeout),
        voice_enabled=False,
    ).validated()

    class OfflineRouter(AIRouter):
        def _request(self, path, body, content_type):  # noqa: ANN001
            raise RouterError("offline evaluation: no model router")

    bridge_server = None
    bridge = None
    planner_type = None
    if args.mode == "live":
        from fake_bridge import start_fixture_bridge
        from openra_ai_companion.interactive_agent import InteractiveMCPPlanner

        bridge_server, bridge, bridge_address = start_fixture_bridge()
        planner_type = (InteractiveMCPPlanner, bridge_address)

    with output.open("a", encoding="utf-8") as stream:
        for case in load_cases():
            if case["id"] not in selected or case["id"] in done:
                continue
            payload = json.loads((HERE / "fixtures" / f"{case['fixture']}.json").read_text(encoding="utf-8"))
            snapshot = GameSnapshot.from_dict(payload["observation"])
            router = OfflineRouter(settings) if args.offline else AIRouter(settings)
            companion = Companion(router=router)
            companion.update_snapshot(snapshot)
            if planner_type is not None:
                bridge.load(payload)
                planner_class, address = planner_type
                companion.set_action_planner(planner_class(address, model=args.model, provider="local", router_url=args.router_url).plan)
            before = router.usage_summary()["chat_calls"]
            started = time.perf_counter()
            record = {"id": case["id"], "fixture": case["fixture"], "utterance": case["utterance"]}
            try:
                response = companion.handle_player_input(case["utterance"])
                record.update({
                    "text": response.text,
                    "source": response.source,
                    "interrupted": response.interrupted,
                    "metadata": _jsonable(response.metadata),
                    "pending_after": companion.pending_action() is not None,
                })
            except Exception as error:  # a crash is a graded failure, not a harness failure
                record["error"] = f"{type(error).__name__}: {error}"[:400]
            record["wall_ms"] = round((time.perf_counter() - started) * 1000)
            calls = router.usage_summary()["chat_calls"] - before
            planner_used = "mcp" in (record.get("metadata") or {})
            record["model_calls"] = calls
            record["model_called"] = bool(calls or planner_used)
            stream.write(json.dumps(record) + "\n")
            stream.flush()
            print(f"{case['id']} {record['wall_ms']:>6}ms {record.get('source', record.get('error', ''))[:40]:40} {case['utterance'][:60]}", flush=True)
    if bridge_server is not None:
        bridge_server.stop(0)
    return 0


# ---------------------------------------------------------------------------
# Parent
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--case-file", help=argparse.SUPPRESS)
    parser.add_argument("--outcomes", help=argparse.SUPPRESS)
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC, help="companion source tree under test")
    parser.add_argument("--mode", choices=("direct", "live"), default="direct")
    parser.add_argument("--router-url", default="")
    parser.add_argument("--model", default="local-coder")
    parser.add_argument("--profile", choices=("lightweight", "recommended"), default="lightweight",
                        help="local AI profile; Windows CPU machines select lightweight automatically")
    parser.add_argument("--external", action="store_true", help="treat the router as an external OpenAI-compatible endpoint")
    parser.add_argument("--timeout", type=float, default=20.0, help="router timeout (the product default is 20 s)")
    parser.add_argument("--start-local-ai", action="store_true")
    parser.add_argument("--ai-root", type=Path, default=REPOSITORY, help="install root containing the ai/ pack")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--only", default="", help="comma-separated case ids or fixture/variant/category names")
    parser.add_argument("--output", type=Path, default=REPOSITORY / ".artifacts" / "nl-orders" / "eval" / "latest")
    parser.add_argument("--label", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--grade-only", action="store_true", help="re-grade an existing outcomes.jsonl in --output")
    args = parser.parse_args()
    if args.worker:
        return worker(args)

    sys.path.insert(0, str(HERE))
    from cases import cases as load_cases
    from grade import grade, summarize

    all_cases = load_cases()
    if args.only:
        wanted = {value.strip() for value in args.only.split(",") if value.strip()}
        all_cases = [case for case in all_cases if wanted & {case["id"], case["fixture"], case["variant"], case["category"], case["split"]}]
    output: Path = args.output
    output.mkdir(parents=True, exist_ok=True)
    outcomes_path = output / "outcomes.jsonl"
    if args.grade_only:
        ran = {json.loads(line)["id"] for line in outcomes_path.read_text(encoding="utf-8").splitlines() if line.strip()}
        all_cases = [case for case in all_cases if case["id"] in ran]
        previous = json.loads((output / "summary.json").read_text(encoding="utf-8")) if (output / "summary.json").is_file() else {}
        args.label = args.label or previous.get("label", "")
        args.src = Path(previous.get("src", str(args.src)))
        args.mode = previous.get("mode", args.mode)
        return _report(args, all_cases, outcomes_path, output, grade, summarize, previous.get("elapsed_seconds", 0),
                       previous.get("router_url", args.router_url))
    if outcomes_path.exists() and not args.resume:
        outcomes_path.unlink()
    case_file = output / "cases.txt"
    case_file.write_text("\n".join(case["id"] for case in all_cases) + "\n", encoding="utf-8")

    gateway = None
    router_url = args.router_url
    try:
        if args.start_local_ai and not args.offline:
            gateway, router_url = start_local_ai(args.ai_root.resolve(), args.profile, output / "local-ai.log")
        if not router_url:
            router_url = "http://127.0.0.1:9"  # unreachable; only valid with --offline
            if not args.offline:
                parser.error("pass --router-url, --start-local-ai or --offline")
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join([str(args.src.resolve()), str(REPOSITORY / "services" / "worldgen" / "src")])
        environment["OPENRA_AI_BRAIN_STATE"] = str(output / "brain-blackboard.jsonl")
        environment["APPDATA"] = str(output / "appdata")
        environment["OPENRA_AI_AGENT_PROVIDER"] = "local"
        environment["OPENRA_AI_AGENT_MODEL"] = args.model
        environment["OPENRA_AI_AGENT_ROUTER_URL"] = router_url
        environment["OPENRA_AI_ROUTER_URL"] = router_url
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment.pop("OPENAI_API_KEY", None)
        (output / "appdata").mkdir(exist_ok=True)
        command = [
            sys.executable, str(Path(__file__).resolve()), "--worker", "--case-file", str(case_file),
            "--outcomes", str(outcomes_path), "--mode", args.mode, "--router-url", router_url,
            "--model", args.model, "--profile", args.profile, "--timeout", str(args.timeout),
        ]
        if args.offline:
            command.append("--offline")
        if args.external:
            command.append("--external")
        started = time.monotonic()
        result = subprocess.run(command, env=environment, cwd=str(REPOSITORY))
        if result.returncode != 0:
            print("worker failed", result.returncode, file=sys.stderr)
            return result.returncode
        elapsed = time.monotonic() - started
    finally:
        stop_process(gateway)
    return _report(args, all_cases, outcomes_path, output, grade, summarize, elapsed, router_url)


def _report(args, all_cases, outcomes_path, output, grade, summarize, elapsed, router_url) -> int:  # noqa: ANN001
    outcomes = [json.loads(line) for line in outcomes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {outcome["id"]: outcome for outcome in outcomes}
    graded = [grade(case, by_id.get(case["id"], {"error": "not run"})) for case in all_cases]
    summary = summarize(all_cases, graded, [by_id.get(case["id"], {"error": "not run"}) for case in all_cases])
    summary.update({
        "label": args.label or ("offline" if args.offline else args.mode),
        "src": str(args.src),
        "mode": args.mode,
        "profile": args.profile,
        "router_url": router_url if not args.offline else "offline",
        "elapsed_seconds": round(elapsed),
    })
    (output / "graded.json").write_text(json.dumps(graded, indent=1) + "\n", encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    lines = [f"# NL order eval: {summary['label']}", "", "```json", json.dumps(summary, indent=1), "```", "", "## Failures", ""]
    for case, entry in zip(all_cases, graded):
        if not entry["passed"]:
            outcome = by_id.get(case["id"], {})
            lines.append(f"- {case['id']} [{case['fixture']}] {case['utterance']!r} ({case['category']}/{case['variant']}): "
                         + "; ".join(entry["problems"])[:400] + f"  -- reply: {str(outcome.get('text', ''))[:160]!r}")
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"by_variant", "by_mod"}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
