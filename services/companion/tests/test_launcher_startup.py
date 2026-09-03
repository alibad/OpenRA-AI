from __future__ import annotations

import unittest
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from openra_ai_companion.cli import _parser
from openra_ai_companion.process_entrypoints import game_mcp_command


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class LauncherStartupTests(unittest.TestCase):

    @unittest.skipUnless(Path("/bin/bash").exists(), "requires bash")
    def test_default_game_selection_accepts_no_launch_arguments(self) -> None:
        wrapper = (REPOSITORY_ROOT / "apps/installer/macos/OpenRAAI").read_text()
        selection = wrapper[wrapper.index('selected_game="ra"'):wrapper.index('\ngame_pid=""')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = 'set -euo pipefail\nsupport_root="$1"\nresources_dir="$1"\nmap_argument=""\nshift\n'
            script += selection + '\nprintf "%s\\n" "${game_args[@]}"\n'
            for extra in ([], ["Game.Mod=ra2"], ["Launch.Map=map with spaces"]):
                with self.subTest(arguments=extra):
                    result = subprocess.run(["/bin/bash", "-c", script, "test", directory, *extra],
                                            check=True, capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.stdout.splitlines(), ["Game.Mod=ra", *extra])
            for name in ("mods/ra2/mod.yaml", "Content/ra2/ra2.mix", "Content/ra2/language.mix"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            (root / "openra-ai-game.txt").write_text("ra2\n")
            result = subprocess.run(["/bin/bash", "-c", script, "test", directory], check=True,
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.stdout.strip(), "Game.Mod=ra2")

    def test_frozen_game_tools_use_the_bundled_dispatcher(self) -> None:
        with patch.object(sys, "frozen", True, create=True):
            self.assertEqual(game_mcp_command("--proposal-mode"), [sys.executable, "game-mcp", "--proposal-mode"])
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(game_mcp_command("--proposal-mode"),
                             [sys.executable, "-m", "openra_ai_companion.game_mcp", "--proposal-mode"])

    def test_bundle_entrypoint_dispatches_game_tools(self) -> None:
        result = subprocess.run([sys.executable, str(REPOSITORY_ROOT / "apps/launcher/companion_entry.py"),
                                 "game-mcp", "--help"], check=True, capture_output=True, text=True, timeout=20)
        self.assertIn("openra-ai-game-mcp", result.stdout)

    @unittest.skipUnless(shutil.which("bash") and shutil.which("pgrep"), "requires process-tree tools")
    def test_wrapper_cleanup_stops_the_game_child(self) -> None:
        wrapper = (REPOSITORY_ROOT / "apps/installer/macos/OpenRAAI").read_text()
        function = wrapper[wrapper.index("stop_process_tree() {"):wrapper.index("\ncleanup() {")]
        process = subprocess.Popen(["bash", "-c", 'sleep 30 & echo "$!"; wait'], stdout=subprocess.PIPE, text=True)
        child = int(process.stdout.readline())
        try:
            subprocess.run(["bash", "-c", function + '\nstop_process_tree "$1"', "test", str(process.pid)], check=True, timeout=5)
            process.wait(timeout=5)
            for _ in range(20):
                try:
                    os.kill(child, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            else:
                self.fail("The game child survived wrapper cleanup")
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            try:
                os.kill(child, 15)
            except ProcessLookupError:
                pass

    def test_final_macos_signature_preserves_apphost_entitlements(self) -> None:
        root = Path(__file__).resolve().parents[3]
        script = (root / "scripts" / "package-macos.sh").read_text()
        deep = script.rindex('codesign --force --deep')
        apphost = script.rindex('--entitlements "$ENTITLEMENTS"')
        final = script.rindex('codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$APP_ROOT"')
        self.assertLess(deep, apphost)
        self.assertLess(apphost, final)

    def test_watch_accepts_wrapper_lifecycle_pid(self) -> None:
        args = _parser().parse_args(["watch", "--parent-pid", "42"])
        self.assertEqual(args.parent_pid, 42)
        self.assertEqual(args.game_pid, 0)

    def test_macos_launcher_waits_for_companion_before_game(self) -> None:
        wrapper = (REPOSITORY_ROOT / "apps/installer/macos/OpenRAAI").read_text(encoding="utf-8")
        companion_start = wrapper.index('"$companion" watch')
        health_wait = wrapper.index("\nwait_for_companion_health\n", companion_start)
        game_start = wrapper.index('"$macos_dir/GameLauncher"', health_wait)

        self.assertLess(companion_start, health_wait)
        self.assertLess(health_wait, game_start)
        self.assertIn('--parent-pid "$$"', wrapper[companion_start:health_wait])
        self.assertNotIn("--game-pid", wrapper[companion_start:health_wait])
        self.assertIn('trap cleanup EXIT INT TERM', wrapper[:companion_start])
        self.assertIn('if [ "${#game_args[@]}" -eq 0 ]; then', wrapper[health_wait:])
        self.assertIn("control_ready", wrapper[:health_wait])
        self.assertIn("OPENRA_AI_COMPANION_READY=1", wrapper[health_wait:game_start])
        self.assertIn("OPENRA_AI_STARTUP_AUTO_ACT", wrapper[health_wait:game_start])
        self.assertIn('OPENRA_AI_VERSION="$map_version"', wrapper[:companion_start])

    def test_macos_apphost_has_dotnet_jit_entitlement(self) -> None:
        entitlements = (
            REPOSITORY_ROOT / "apps/installer/macos/OpenRAAI.entitlements"
        ).read_text(encoding="utf-8")
        package_script = (REPOSITORY_ROOT / "scripts/package-macos.sh").read_text(encoding="utf-8")

        self.assertIn("com.apple.security.cs.allow-jit", entitlements)
        self.assertIn('--entitlements "$ENTITLEMENTS"', package_script)
        self.assertIn('"$MACOS/apphost-$ARCH_DIR"', package_script)

    def test_macos_package_relocates_homebrew_brotli(self) -> None:
        package_script = (REPOSITORY_ROOT / "scripts/package-macos.sh").read_text(encoding="utf-8")

        self.assertIn("libSystem.IO.Compression.Native.dylib", package_script)
        self.assertIn('"@loader_path/$library_name"', package_script)
        self.assertIn("macOS package has non-portable dependencies", package_script)


if __name__ == "__main__":
    unittest.main()
