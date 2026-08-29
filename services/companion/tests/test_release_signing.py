from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RELEASE_SPEC = importlib.util.spec_from_file_location(
    "openra_ai_release", REPOSITORY_ROOT / "scripts/release.py"
)
assert RELEASE_SPEC and RELEASE_SPEC.loader
RELEASE = importlib.util.module_from_spec(RELEASE_SPEC)
RELEASE_SPEC.loader.exec_module(RELEASE)


class ReleaseSigningTests(unittest.TestCase):
    def test_official_commands_enforce_platform_signing(self) -> None:
        with mock.patch.object(RELEASE.subprocess, "run") as run:
            RELEASE.run_command(
                {"program": "powershell.exe", "arguments": ["package.ps1"]},
                "0.1.0-alpha.14",
                False,
                official=True,
            )

        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["OPENRA_AI_OFFICIAL_RELEASE"], "1")
        self.assertEqual(os.environ.get("OPENRA_AI_OFFICIAL_RELEASE"), None)

    def test_windows_signing_uses_certificate_store_not_committed_credentials(self) -> None:
        signing_script = (REPOSITORY_ROOT / "scripts/sign-windows-artifacts.ps1").read_text(encoding="utf-8")
        package_script = (REPOSITORY_ROOT / "scripts/package-windows.ps1").read_text(encoding="utf-8")
        installer_script = (REPOSITORY_ROOT / "scripts/package-windows-installer.ps1").read_text(encoding="utf-8")
        nsis_script = (REPOSITORY_ROOT / "apps/installer/windows/OpenRAAI.nsi").read_text(encoding="utf-8")
        installer_smoke = (REPOSITORY_ROOT / "scripts/smoke-windows-installer.ps1").read_text(encoding="utf-8")

        self.assertIn("WINDOWS_SIGNING_CERTIFICATE_THUMBPRINT", signing_script)
        self.assertIn('Cert:\\$store\\My\\$thumbprint', signing_script)
        self.assertNotIn("CertificatePassword", signing_script)
        self.assertIn("openra-ai-companion.exe", package_script)
        self.assertIn("openra-ai-runtime.exe", package_script)
        self.assertIn("OpenRA-AI.exe", package_script)
        self.assertIn("OpenRA.Server.exe", package_script)
        self.assertIn("OpenRA.Utility.exe", package_script)
        self.assertIn("$installer", installer_script)
        self.assertIn("-VerifyOnly", installer_script)
        self.assertIn("/DUNINSTALLSIGNER=", installer_script)
        self.assertIn("!uninstfinalize", nsis_script)
        self.assertIn("Uninstall OpenRA AI.exe", installer_smoke)


if __name__ == "__main__":
    unittest.main()
