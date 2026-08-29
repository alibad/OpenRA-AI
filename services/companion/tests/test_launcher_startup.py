from __future__ import annotations

import unittest
from pathlib import Path

from openra_ai_companion.cli import _parser


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class LauncherStartupTests(unittest.TestCase):
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
