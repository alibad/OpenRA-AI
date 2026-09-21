from pathlib import Path
import json
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from openra_ai_companion.game_content import import_owned_ra2, owned_ra2_candidates, steam_roots

ROOT = Path(__file__).resolve().parents[3]


class WindowsGameSetupTests(unittest.TestCase):
    def test_discovers_owned_game_in_registered_secondary_library(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steamapps = root / "steamapps"
            game = steamapps / "common/Game With Spaces"
            game.mkdir(parents=True)
            (steamapps / "appmanifest_2229850.acf").write_text('"installdir" "Game With Spaces"')
            (game / "RA2.MIX").write_bytes(b"ra2" * 1024)
            (game / "LANGUAGE.MIX").write_bytes(b"language" * 1024)
            support = root / "support"
            with patch("openra_ai_companion.game_content.Path.home", return_value=root), \
                    patch("openra_ai_companion.game_content.steam_roots", return_value=[root]), \
                    patch.dict(os.environ, {"OPENRA_AI_SUPPORT_DIR": str(support)}):
                self.assertTrue(import_owned_ra2()["installed"])
                self.assertEqual((support / "Content/ra2/ra2.mix").read_bytes(), (game / "RA2.MIX").read_bytes())
                self.assertTrue(import_owned_ra2()["already_installed"])

    def test_manifest_cannot_escape_steam_library(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "steamapps").mkdir()
            (root / "steamapps/appmanifest_2229850.acf").write_text('"installdir" "../../outside"')
            with patch("openra_ai_companion.game_content.steam_roots", return_value=[root]), patch.dict(os.environ, {"OPENRA_AI_RA2_CONTENT_DIR": ""}):
                self.assertNotIn((root / "outside", root / "outside"), owned_ra2_candidates())

    def test_missing_content_is_actionable_and_does_not_create_dummy_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("openra_ai_companion.game_content.owned_ra2_candidates", return_value=[]), patch.dict(os.environ, {"OPENRA_AI_SUPPORT_DIR": directory}):
                with self.assertRaisesRegex(ValueError, "2229850"):
                    import_owned_ra2()
                self.assertFalse((Path(directory) / "Content/ra2/ra2.mix").exists())

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell launcher")
    def test_launcher_preserves_quoted_arguments_and_accepts_both_games(self):
        canonical = ROOT.parent / "OpenRA"
        for mod in ("ra", "ra2"):
            with tempfile.TemporaryDirectory(prefix="openra space ") as directory:
                root = Path(directory)
                (root / "bin").mkdir()
                (root / "bin/OpenRA.exe").touch()
                shutil.copy2(canonical / "launch-game.ps1", root / "launch-game.ps1")
                result = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(root / "launch-game.ps1"), "-ValidateOnly", "-NoCompanion", f"Game.Mod={mod}", "Launch.Map=map with spaces.oramap"], text=True, capture_output=True, check=True)
                value = json.loads(result.stdout)
                self.assertEqual(value["Mod"], mod)
                self.assertFalse(value["CompanionRequested"])
                self.assertIn("Launch.Map=map with spaces.oramap", value["Arguments"])

    def test_windows_package_prepares_both_games_without_replacing_engine_library(self):
        script = (ROOT / "scripts/package-windows.ps1").read_text(encoding="utf-8")
        self.assertLess(script.index('"prepare-ra2.py"'), script.index('& $signingScript'))
        self.assertIn('--runtime win-x64 --data-only', script)
        self.assertIn('"launch-game.ps1"', script)
        self.assertIn('games = @("ra", "ra2")', script)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell installer")
    def test_installer_accepts_verified_adjacent_pack_and_rejects_wrong_digest(self):
        with tempfile.TemporaryDirectory(prefix="openra pack ") as directory:
            root = Path(directory)
            archive = root / "AI pack.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("pack.json", '{"pack_version":"fixture"}')
                bundle.writestr("models/test.bin", b"test model")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            destination = root / "install/ai"
            command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                       str(ROOT / "apps/launcher/Install-AIPack.ps1"), "-SourceArchive", str(archive),
                       "-Destination", str(destination), "-SHA256"]
            # Python can inherit PowerShell 7's module path. Windows PowerShell 5
            # must discover its own modules, as it does when started by NSIS.
            environment = {key: value for key, value in os.environ.items() if key.lower() != "psmodulepath"}
            installed = subprocess.run([*command, digest], capture_output=True, text=True, env=environment)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            self.assertEqual((destination / "models/test.bin").read_bytes(), b"test model")
            failed = subprocess.run([*command, "0" * 64], capture_output=True, text=True, env=environment)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("checksum mismatch", failed.stderr)
            self.assertEqual((destination / "models/test.bin").read_bytes(), b"test model")


if __name__ == "__main__":
    unittest.main()
