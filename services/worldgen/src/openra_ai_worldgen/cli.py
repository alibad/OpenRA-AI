from __future__ import annotations

import argparse
import json
from pathlib import Path

from .generator import MissionGenerator
from .models import GeoSelection
from .server import serve
from .validator import validate_package


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openra-ai-worldgen")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="generate a playable .oramap package")
    generate.add_argument("--lat", type=float, required=True)
    generate.add_argument("--lon", type=float, required=True)
    generate.add_argument("--title", default="Earth Skirmish")
    generate.add_argument("--radius", type=int, default=3500)
    generate.add_argument("--size", type=int, choices=(64, 96, 128), default=64)
    generate.add_argument("--seed", type=int, default=1)
    generate.add_argument("--story", default="")
    generate.add_argument("--output", type=Path, default=Path("generated/missions"))
    generate.add_argument("--fixture", type=Path)
    generate.add_argument("--offline", action="store_true")
    validate = commands.add_parser("validate", help="validate an OpenRA map package")
    validate.add_argument("package", type=Path)
    server = commands.add_parser("serve", help="start the local HTTP service")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8788)
    server.add_argument("--output", type=Path, default=Path("generated/missions"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate":
        selection = GeoSelection(args.lat, args.lon, args.title, args.radius, args.size, args.seed, "offline" if args.offline else "openstreetmap", args.story)
        result = MissionGenerator(args.fixture, allow_network=not args.offline).generate(selection, args.output)
        print(json.dumps(result.as_dict(), indent=2))
        return 0
    if args.command == "validate":
        report = validate_package(args.package)
        print(json.dumps(report.as_dict(), indent=2))
        return 0 if report.valid else 1
    serve(args.host, args.port, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
