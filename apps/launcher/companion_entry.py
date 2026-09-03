import sys

from openra_ai_companion.cli import main as companion_main


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "game-mcp":
        from openra_ai_companion.game_mcp import main as game_mcp_main
        return game_mcp_main(arguments[1:])
    return companion_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
