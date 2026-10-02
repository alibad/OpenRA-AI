import sys


def _line_buffered_output():
    """The game logs the sidecar's stdout/stderr to files; a frozen build ignores PYTHONUNBUFFERED."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(line_buffering=True)
            except (ValueError, OSError):
                pass


def main(argv=None):
    _line_buffered_output()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "game-mcp":
        from openra_ai_companion.game_mcp import main as game_mcp_main
        return game_mcp_main(arguments[1:])
    if arguments and arguments[0] == "runtime":
        # One frozen executable also hosts the loopback AI gateway (RTS AI mod bundle).
        from openra_ai_companion.local_runtime import main as runtime_main
        return runtime_main(arguments[1:])
    if arguments and arguments[0] == "pack":
        # Checksum-verified AI pack install, run by the RTS AI installer.
        from openra_ai_companion.pack_cli import main as pack_main
        return pack_main(arguments[1:])
    from openra_ai_companion.cli import main as companion_main
    return companion_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
