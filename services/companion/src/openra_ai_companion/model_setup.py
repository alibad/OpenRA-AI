from __future__ import annotations

import atexit
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Companion


LOCAL_ROUTER_URL = "http://127.0.0.1:4000"


class LocalAISetupError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reachable(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status < 500
    except (OSError, TimeoutError, urllib.error.URLError):
        return False


class LocalAIManager:
    """Installs the checksum-pinned local models and owns their gateway process."""

    def __init__(
        self,
        companion: Companion,
        *,
        lock_path: Path | None = None,
        install_root: Path | None = None,
        runtime_executable: Path | None = None,
        runtime_root: Path | None = None,
        auto_start: bool = True,
    ):
        self.companion = companion
        self.lock_path = lock_path or self._environment_path("OPENRA_AI_PACK_LOCK")
        self.install_root = install_root or self._environment_path("OPENRA_AI_MODEL_ROOT")
        self.runtime_executable = runtime_executable or self._environment_path("OPENRA_AI_RUNTIME_EXECUTABLE")
        self.runtime_root = runtime_root or self._environment_path("OPENRA_AI_BUNDLED_RUNTIME")
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._log_handles: list[object] = []
        self._worker: threading.Thread | None = None
        self._state = "not_installed"
        self._detail = "Install the Local AI Pack to enable private on-device answers and voice."
        self._downloaded_bytes = 0
        self._total_bytes = 0
        self._active_component = ""
        self._manifest: dict | None = None
        self._load_manifest()
        atexit.register(self.stop)

        if not self.supported:
            self._state = "unsupported"
            self._detail = (
                "Local AI requires macOS 13.3 or newer."
                if not self._platform_supported()
                else "This build does not include a compatible local AI runtime."
            )
        elif self.installed:
            self._state = "ready"
            self._detail = "Local AI Pack is installed."
            if auto_start and self.companion.router.settings.model_provider == "local":
                self._start_worker(self._start_runtime_safely)

    @staticmethod
    def _environment_path(name: str) -> Path | None:
        value = os.environ.get(name, "").strip()
        return Path(value).expanduser().resolve() if value else None

    def _load_manifest(self) -> None:
        if not self.lock_path or not self.lock_path.is_file():
            return
        try:
            value = json.loads(self.lock_path.read_text(encoding="utf-8"))
            components = value.get("components")
            if value.get("schema_version") != 1 or not isinstance(components, list) or not components:
                raise ValueError("invalid local AI pack manifest")
            for component in components:
                destination = PurePosixPath(str(component.get("destination", "")))
                digest = str(component.get("sha256", "")).lower()
                if (
                    destination.is_absolute()
                    or not destination.parts
                    or ".." in destination.parts
                    or not str(component.get("url", "")).startswith("https://")
                    or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)
                    or int(component.get("bytes", 0)) <= 0
                ):
                    raise ValueError(f"invalid component {component.get('id', 'unknown')}")
            self._manifest = value
            self._total_bytes = sum(int(component["bytes"]) for component in components)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self._state = "unsupported"
            self._detail = f"The bundled Local AI Pack manifest is invalid: {exc}"

    @property
    def supported(self) -> bool:
        executable_suffix = ".exe" if os.name == "nt" else ""
        return bool(
            self._manifest
            and self._platform_supported()
            and self.install_root
            and self.runtime_executable
            and self.runtime_executable.is_file()
            and self.runtime_root
            and self.runtime_root.is_dir()
            and (self.runtime_root / "llama" / f"llama-server{executable_suffix}").is_file()
            and (self.runtime_root / "whisper" / f"whisper-server{executable_suffix}").is_file()
        )

    @staticmethod
    def _platform_supported() -> bool:
        if sys.platform != "darwin":
            return True
        version = platform.mac_ver()[0].split(".")
        try:
            major = int(version[0])
            minor = int(version[1]) if len(version) > 1 else 0
        except (ValueError, IndexError):
            return False
        return (major, minor) >= (13, 3)

    @property
    def pack_root(self) -> Path | None:
        return self.install_root / "ai" if self.install_root else None

    @property
    def receipt_path(self) -> Path | None:
        return self.pack_root / "pack.json" if self.pack_root else None

    @property
    def installed(self) -> bool:
        if not self._manifest or not self.pack_root or not self.receipt_path or not self.receipt_path.is_file():
            return False
        try:
            receipt = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if receipt.get("pack_version") != self._manifest.get("pack_version"):
            return False
        return all(
            (self.pack_root / Path(*PurePosixPath(component["destination"]).parts)).is_file()
            and (self.pack_root / Path(*PurePosixPath(component["destination"]).parts)).stat().st_size
            == int(component["bytes"])
            for component in self._manifest["components"]
        )

    def status(self) -> dict[str, object]:
        with self._lock:
            state = self._state
            detail = self._detail
            process = self._process
            if process and process.poll() is not None and state in {"starting", "running"}:
                state = "error"
                detail = "The local AI service exited. Select Retry to start it again."
                self._state = state
                self._detail = detail
            elif state == "running" and not _reachable(f"{LOCAL_ROUTER_URL}/health/liveliness"):
                state = "starting"
                detail = "Local models are loading…"
                self._state = state
                self._detail = detail
            downloaded = self._downloaded_bytes
            total = self._total_bytes
            progress = round(downloaded / total * 100) if total else 0
            requirements = dict((self._manifest or {}).get("hardware_requirements") or {})
            return {
                "supported": self.supported,
                "installed": self.installed,
                "state": state,
                "detail": detail,
                "pack_version": str((self._manifest or {}).get("pack_version", "")),
                "downloaded_bytes": downloaded,
                "total_bytes": total,
                "progress_percent": max(0, min(100, progress)),
                "active_component": self._active_component,
                "hardware_requirements": requirements,
            }

    def install(self) -> dict[str, object]:
        if not self.supported:
            raise LocalAISetupError("Local AI installation is unavailable in this build.")
        with self._lock:
            if self._worker and self._worker.is_alive():
                return self.status()
            self._state = "installing"
            self._detail = "Preparing the Local AI Pack download…"
            self._downloaded_bytes = 0
            self._active_component = ""
            self._start_worker(self._install_and_start)
            return self.status()

    def retry(self) -> dict[str, object]:
        if self.installed:
            with self._lock:
                if self._worker and self._worker.is_alive():
                    return self.status()
                self._start_worker(self._start_runtime_safely)
                return self.status()
        return self.install()

    def _start_worker(self, target) -> None:
        self._worker = threading.Thread(target=target, name="OpenRA-AI-local-setup", daemon=True)
        self._worker.start()

    def _start_runtime_safely(self) -> None:
        try:
            self._start_runtime()
        except Exception as exc:
            with self._lock:
                self._state = "error"
                self._detail = str(exc)[:500]

    def _install_and_start(self) -> None:
        try:
            assert self._manifest is not None and self.pack_root is not None
            self.pack_root.mkdir(parents=True, exist_ok=True)
            available = shutil.disk_usage(self.pack_root).free
            remaining = sum(int(component["bytes"]) for component in self._manifest["components"])
            if available < remaining + 512 * 1024 * 1024:
                raise LocalAISetupError(
                    f"Local AI needs about {remaining / 1024 / 1024 / 1024:.1f} GB plus working space, "
                    f"but only {available / 1024 / 1024 / 1024:.1f} GB is free."
                )
            for component in self._manifest["components"]:
                self._install_component(component)
            receipt = {
                "schema_version": 1,
                "name": self._manifest.get("name", "OpenRA AI Local AI Pack"),
                "pack_version": self._manifest["pack_version"],
                "installed_at": int(time.time()),
                "components": [
                    {
                        "id": component["id"],
                        "sha256": component["sha256"],
                        "bytes": component["bytes"],
                        "destination": component["destination"],
                    }
                    for component in self._manifest["components"]
                ],
            }
            temporary = self.receipt_path.with_suffix(".json.partial")
            temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temporary, self.receipt_path)
            with self._lock:
                self._downloaded_bytes = self._total_bytes
                self._active_component = ""
                self._state = "ready"
                self._detail = "Local AI Pack installed. Starting the model service…"
            self._start_runtime()
        except Exception as exc:
            with self._lock:
                self._state = "error"
                self._detail = str(exc)[:500]

    def _install_component(self, component: dict) -> None:
        assert self.pack_root is not None
        destination = self.pack_root / Path(*PurePosixPath(component["destination"]).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected_bytes = int(component["bytes"])
        expected_digest = str(component["sha256"])
        with self._lock:
            self._active_component = str(component.get("id", "model"))
            self._detail = f"Downloading {self._active_component}…"

        if destination.is_file() and destination.stat().st_size == expected_bytes:
            if _sha256(destination) == expected_digest:
                with self._lock:
                    self._downloaded_bytes += expected_bytes
                return
            destination.unlink()

        partial = destination.with_name(destination.name + ".partial")
        existing = partial.stat().st_size if partial.is_file() else 0
        if existing > expected_bytes:
            partial.unlink()
            existing = 0
        headers = {"User-Agent": "OpenRA-AI-Setup/1"}
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = urllib.request.Request(str(component["url"]), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                resumed = existing > 0 and response.status == 206
                mode = "ab" if resumed else "wb"
                if not resumed:
                    existing = 0
                with partial.open(mode) as output:
                    with self._lock:
                        self._downloaded_bytes += existing
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        output.write(block)
                        with self._lock:
                            self._downloaded_bytes += len(block)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise LocalAISetupError(f"Download failed for {component['id']}: {exc}") from exc
        if partial.stat().st_size != expected_bytes:
            raise LocalAISetupError(
                f"Size verification failed for {component['id']}: expected {expected_bytes}, got {partial.stat().st_size}."
            )
        if _sha256(partial) != expected_digest:
            partial.unlink()
            raise LocalAISetupError(f"Security check failed for {component['id']}: SHA-256 does not match.")
        os.replace(partial, destination)

    def _start_runtime(self) -> None:
        if not self.supported or not self.installed:
            return
        with self._lock:
            if _reachable(f"{LOCAL_ROUTER_URL}/health/liveliness"):
                self._configure_local_route()
                self._state = "running"
                self._detail = "Local AI is installed and ready. Voice stays on this Mac."
                return
            if self._process and self._process.poll() is None:
                return
            self._state = "starting"
            self._detail = "Local models are loading…"
            assert self.install_root and self.runtime_executable and self.runtime_root
            log_directory = self.install_root / "logs"
            log_directory.mkdir(parents=True, exist_ok=True)
            output = (log_directory / "runtime.out.log").open("ab")
            error = (log_directory / "runtime.err.log").open("ab")
            self._log_handles.extend((output, error))
            self._process = subprocess.Popen(
                [
                    str(self.runtime_executable),
                    "serve",
                    "--root",
                    str(self.install_root),
                    "--runtime-root",
                    str(self.runtime_root),
                    "--mode",
                    "local",
                    "--parent-pid",
                    str(os.getpid()),
                ],
                cwd=self.runtime_executable.parent,
                stdout=output,
                stderr=error,
            )

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self._process and self._process.poll() is not None:
                raise LocalAISetupError(
                    "The local model service could not start. Select Retry; details are in runtime.err.log."
                )
            if _reachable(f"{LOCAL_ROUTER_URL}/health/liveliness"):
                self._configure_local_route()
                with self._lock:
                    self._state = "running"
                    self._detail = "Local AI is installed and ready. Voice stays on this Mac."
                return
            time.sleep(0.5)
        raise LocalAISetupError("Local models did not finish loading within three minutes. Select Retry.")

    def _configure_local_route(self) -> None:
        self.companion.router.configure(
            {
                "router_url": LOCAL_ROUTER_URL,
                "model_provider": "local",
                "text_model": "local-coder",
                "vision_model": "local-coder",
                "transcribe_model": "local-whisper",
                "speech_model": "local-kokoro",
            }
        )
        self.companion.apply_settings()

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        for handle in self._log_handles:
            try:
                handle.close()
            except Exception:
                pass
        self._log_handles.clear()
