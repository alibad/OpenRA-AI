from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("ra2_preview", ROOT / "scripts/build-ra2-preview.py")
assert SPEC and SPEC.loader
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)


class RA2PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = self.root / "base"
        self.language = self.root / "english"
        self.destination = self.root / "private-content"
        self.base.mkdir()
        self.language.mkdir()
        (self.base / "RA2.MIX").write_bytes(b"base" * 1024)
        (self.language / "language.mix").write_bytes(b"english" * 1024)

    def test_import_is_case_insensitive_and_hash_verified(self):
        hashes = preview.import_content(self.base, self.language, self.destination)
        self.assertEqual(hashes["ra2.mix"], hashlib.sha256(b"base" * 1024).hexdigest())
        self.assertEqual((self.destination / "language.mix").read_bytes(), b"english" * 1024)
        self.assertEqual(hashes, preview.import_content(self.base, self.language, self.destination))

    def test_import_refuses_to_overwrite_other_game_data(self):
        self.destination.mkdir()
        target = self.destination / "ra2.mix"
        target.write_bytes(b"existing")
        with self.assertRaisesRegex(ValueError, "Refusing to replace"):
            preview.import_content(self.base, self.language, self.destination)
        self.assertEqual(target.read_bytes(), b"existing")
        self.assertFalse((self.destination / "language.mix").exists())

    def test_import_rejects_symlink_target(self):
        self.destination.mkdir()
        (self.destination / "ra2.mix").symlink_to(self.base / "RA2.MIX")
        with self.assertRaisesRegex(ValueError, "Refusing to replace"):
            preview.import_content(self.base, self.language, self.destination)

    def test_missing_or_truncated_language_archive_does_not_import_base(self):
        (self.language / "language.mix").write_bytes(b"stub")
        with self.assertRaisesRegex(ValueError, "not a complete"):
            preview.import_content(self.base, self.language, self.destination)
        self.assertFalse(self.destination.exists())

    def test_conflicting_archive_casing_is_rejected(self):
        with patch.object(Path, "iterdir", return_value=[
            self.base / "RA2.MIX", self.base / "ra2.mix"
        ]), self.assertRaisesRegex(ValueError, "Expected one"):
            preview.content_file(self.base, "ra2.mix")

    def archive(self, entries):
        path = self.root / "source.tar.gz"
        with tarfile.open(path, "w:gz") as bundle:
            for name, kind in entries:
                entry = tarfile.TarInfo(name)
                if kind == "link":
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = "/tmp/escape"
                    bundle.addfile(entry)
                else:
                    entry.size = 4
                    bundle.addfile(entry, io.BytesIO(b"data"))
        return path

    def test_source_excludes_hosted_workflows(self):
        archive = self.archive([
            ("ra2-test/mods/ra2/mod.yaml", "file"),
            ("ra2-test/.github/workflows/build.yml", "file"),
        ])
        source = preview.extract_source(archive, self.root / "extract", "test")
        self.assertTrue((source / "mods/ra2/mod.yaml").exists())
        self.assertFalse((source / ".github").exists())

    def test_source_rejects_traversal_and_links_before_extracting(self):
        for unsafe, kind in (("ra2-test/../../escape", "file"), ("ra2-test/link", "link")):
            with self.subTest(unsafe=unsafe):
                archive = self.archive([("ra2-test/good", "file"), (unsafe, kind)])
                with self.assertRaises(ValueError):
                    preview.extract_source(archive, self.root / "extract", "test")
                self.assertFalse((self.root / "extract").exists())

    def test_cached_source_checksum_failure_is_closed(self):
        cache = self.root / "cache"
        cache.mkdir()
        archive = cache / "ra2-test.tar.gz"
        archive.write_bytes(b"incorrect")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            preview.download_source({"commit": "test", "archive_sha256": "0" * 64}, cache)
        self.assertEqual(archive.read_bytes(), b"incorrect")

    def test_preview_identity_and_scope_are_explicit(self):
        config = ROOT / "apps/installer/ra2"
        manifest = json.loads((config / "upstream.json").read_text())
        plist = plistlib.loads((config / "Info.plist").read_bytes())
        self.assertEqual(plist["CFBundleShortVersionString"], manifest["version"])
        self.assertNotEqual(plist["CFBundleIdentifier"], "net.rtsai.openraai")
        launcher = (config / "Program.cs").read_text()
        self.assertIn('"Game.Mod=ra2"', launcher)
        self.assertNotIn("Launch.Map=", launcher)
        patch = (config / "compatibility.patch").read_text()
        self.assertIn("original campaigns and Yuri’s Revenge are not included", patch)
        self.assertIn("+\tWindowTitle: ra2-preview-window-title", patch)
        self.assertNotIn("diff --git a/.github", patch)

    def test_port_covers_runtime_dependencies_not_only_yaml_lint(self):
        compatibility = (ROOT / "apps/installer/ra2/compatibility.patch").read_text()
        for dependency in ("+\tVoxelCache:", "+\tModelRenderer:", "+\tSkirmishLogic",
                           "+\tcommon|chrome/settings-gameplay.yaml"):
            self.assertIn(dependency, compatibility)
        self.assertIn("-\tLobbySettingsNotification", compatibility)
        self.assertIn("+\tImage: common|native-ra2-glyphs.png", compatibility)
        project = (ROOT / "apps/installer/ra2/RA2Launcher.csproj").read_text()
        self.assertNotIn("OpenRA.Mods.Common.csproj", project)
        script = (ROOT / "scripts/build-ra2-preview.py").read_text()
        self.assertIn('run("ditto", app, install)', script)
        self.assertIn('resources / "mods/common/native-ra2-glyphs.png"', script)
        self.assertIn('ROOT / "apps/installer/macos/OpenRAAI.entitlements", app)', script)


if __name__ == "__main__":
    unittest.main()
