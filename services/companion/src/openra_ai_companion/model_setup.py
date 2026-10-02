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

from .model_selection import (
    Hardware,
    choose_profile,
    selected_components,
    selection_status,
    validate_profiles,
    voice_only_profile,
)
from .settings import HOSTED_MODEL

if TYPE_CHECKING:
    from .core import Companion


LOCAL_ROUTER_URL = os.environ.get("OPENRA_AI_LOCAL_ROUTER_URL", "http://127.0.0.1:4000")


def gateway_mode(model_provider: str) -> str:
    """Map the companion's provider setting to the loopback gateway mode it needs."""
    return {"local": "local", "hosted": "hosted", "custom": "external"}.get(model_provider, "unmanaged")


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
        self._profile: dict = {}
        self._hardware = Hardware.detect()
        self._preference = companion.router.settings.model_selection
        # Gateway routing chosen once per launch: local models, an external
        # OpenAI-compatible endpoint, or the hosted RTS AI proxy with local voice.
        self.mode = gateway_mode(companion.router.settings.model_provider)
        self._gateway_state = "stopped"
        self._load_manifest()
        atexit.register(self.stop)

        if self.mode in {"hosted", "external"} and self.gateway_supported:
            # The hosted brain and External endpoints need only the loopback
            # gateway, never the model pack. In hosted mode the pack state below
            # describes the optional ~270 MB voice pack.
            if self.mode == "hosted" and self.supported and self.installed:
                self._state = "ready"
                self._detail = "Voice pack installed."
            elif self.mode == "hosted" and self.supported:
                self._detail = "Hosted AI needs no download. Install the voice pack (about 270 MB) to talk to the co-commander."
            elif self.mode == "hosted":
                self._state = "unsupported"
                self._detail = "Hosted AI is available; local voice is not included in this build."
            elif self.mode == "external":
                self._state = "ready"
                self._detail = "External AI endpoint configured."
            if auto_start:
                self._start_worker(self._start_runtime_safely)
        elif not self.supported and self._state != "unsupported":
            self._state = "unsupported"
            self._detail = (
                "Local AI requires macOS 13.3 or newer."
                if not self._platform_supported()
                else "This build does not include a compatible local AI runtime."
            )
        elif self.installed:
            self._state = "ready"
            self._detail = "Local AI Pack is installed."
            if auto_start and (self.companion.router.settings.model_provider == "local" or
                               self.companion.router.settings.transcribe_model == "local-whisper" or
                               self.companion.router.settings.speech_model == "local-kokoro"):
                self._start_worker(self._start_runtime_safely)

    @property
    def gateway_supported(self) -> bool:
        """The loopback gateway can run without any model files (hosted and External modes)."""
        return bool(
            self._platform_supported()
            and self.install_root
            and self.runtime_executable
            and self.runtime_executable.is_file()
        )

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
            for component in [*components, *value.get("optional_components", [])]:
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
            validate_profiles(value)
            if self.mode == "hosted":
                self._profile = self._hosted_profile(value)
            else:
                self._profile = choose_profile(value, self._hardware, self._preference)
            components = selected_components(value, self._profile)
            value = {**value, "components": components}
            self._manifest = value
            self._total_bytes = sum(int(component["bytes"]) for component in components)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self._state = "unsupported"
            self._detail = f"The bundled Local AI Pack manifest is invalid: {exc}"

    def _hosted_profile(self, manifest: dict) -> dict:
        """Voice-only download, unless a full local model is already installed to serve as the fallback brain."""
        try:
            local = choose_profile(manifest, self._hardware, self._preference)
        except ValueError:
            local = {}
        if local and self.install_root and local.get("model"):
            pack_root = self.install_root / "ai"
            paths = [local["model"], *([local["projector"]] if local.get("projector") else [])]
            if all((pack_root / Path(*PurePosixPath(path).parts)).is_file() for path in paths):
                return local
        return voice_only_profile(manifest) or local

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
            gateway = self._gateway_state
            if process and process.poll() is not None and gateway in {"starting", "running"}:
                gateway = self._gateway_state = "error"
            downloaded = self._downloaded_bytes
            total = self._total_bytes
            progress = round(downloaded / total * 100) if total else 0
            requirements = dict((self._manifest or {}).get("hardware_requirements") or {})
            if self.mode in {"hosted", "external"}:
                return self._gateway_status(state, detail, gateway, downloaded, total, progress, requirements)
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
                "selection": selection_status(self._profile, self._hardware, self._preference),
                "catalogue_version": str((self._manifest or {}).get("catalogue_version", "")),
                "pending_restart": self.companion.router.settings.model_selection != self._preference,
                "capabilities": {
                    "assistant": "ready" if state == "running" else state,
                    "map_images": ("ready" if state == "running" else state) if self._profile.get("projector") else "not_in_profile",
                    "voice_input": "ready" if state == "running" else state,
                    "spoken_replies": "available_on_demand" if state == "running" else state,
                    "voice_language": "English",
                },
            }

    def _gateway_status(self, state: str, detail: str, gateway: str, downloaded: int, total: int,
                        progress: int, requirements: dict) -> dict[str, object]:
        """Status for hosted/External modes: brain readiness from the gateway, voice from the pack."""
        hosted: dict = {}
        if gateway == "running":
            try:
                with urllib.request.urlopen(f"{LOCAL_ROUTER_URL}/health/liveliness", timeout=0.5) as response:
                    hosted = dict(json.loads(response.read()).get("hosted") or {})
            except (OSError, TimeoutError, ValueError, urllib.error.URLError):
                gateway = "starting"
        brain = gateway if gateway != "running" else ("hosted" if self.mode == "hosted" else "external")
        voice = state if self.mode == "hosted" else "external"
        return {
            "mode": self.mode,
            "supported": self.supported,
            "installed": self.installed,
            "state": state,
            "detail": detail,
            "gateway": {"state": gateway, "url": LOCAL_ROUTER_URL},
            "hosted": hosted,
            "pack_version": str((self._manifest or {}).get("pack_version", "")),
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "progress_percent": max(0, min(100, progress)),
            "active_component": self._active_component,
            "hardware_requirements": requirements,
            "selection": selection_status(self._profile, self._hardware, self._preference),
            "catalogue_version": str((self._manifest or {}).get("catalogue_version", "")),
            "pending_restart": False,
            "capabilities": {
                "assistant": brain,
                "map_images": brain,
                "voice_input": "ready" if voice == "running" else voice,
                "spoken_replies": "available_on_demand" if voice == "running" else voice,
                "voice_language": "English",
            },
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
        if self.installed or (self.mode in {"hosted", "external"} and self._gateway_state == "error"):
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
                "profile": self._profile,
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
            if self.mode == "hosted":
                # The running gateway started without speech; restart it with the new voice models.
                self.stop()
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

    def _ready_detail(self, voice_ready: bool) -> str:
        if self.mode == "hosted":
            return ("Hosted AI is ready. Voice stays on this device." if voice_ready else
                    "Hosted AI is ready. Install the voice pack (about 270 MB) to talk to the co-commander.")
        if self.mode == "external":
            return "Your external AI endpoint is connected through the local gateway."
        return "Local AI is installed and ready. Voice stays on this device."

    def _start_runtime(self) -> None:
        if self.mode in {"hosted", "external"}:
            if not self.gateway_supported:
                return
        elif not self.supported or not self.installed:
            return
        # In hosted mode the pack state tracks the optional voice pack only.
        voice_ready = self.mode != "hosted" or (self.supported and self.installed)
        with self._lock:
            if _reachable(f"{LOCAL_ROUTER_URL}/health/liveliness"):
                self._gateway_state = "running"
                self._configure_route()
                if voice_ready:
                    self._state = "running"
                self._detail = self._ready_detail(voice_ready)
                return
            if self._process and self._process.poll() is None:
                return
            self._gateway_state = "starting"
            if voice_ready:
                self._state = "starting"
                self._detail = "Local models are loading…" if self.mode == "local" else "Starting the AI gateway…"
            assert self.install_root and self.runtime_executable
            log_directory = self.install_root / "logs"
            log_directory.mkdir(parents=True, exist_ok=True)
            output = (log_directory / "runtime.out.log").open("ab")
            error = (log_directory / "runtime.err.log").open("ab")
            self._log_handles.extend((output, error))
            self._process = subprocess.Popen(
                [
                    str(self.runtime_executable),
                    *(["-m", "openra_ai_companion.local_runtime"] if os.environ.get("OPENRA_AI_RUNTIME_PYTHON") == "1" else []),
                    "serve",
                    "--port", LOCAL_ROUTER_URL.rsplit(":", 1)[-1],
                    "--root",
                    str(self.install_root),
                    *(["--runtime-root", str(self.runtime_root)] if self.runtime_root else []),
                    "--mode",
                    self.mode,
                    "--parent-pid",
                    str(os.getpid()),
                    "--model-profile", json.dumps(self._profile),
                ],
                cwd=self.runtime_executable.parent,
                stdout=output,
                stderr=error,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self._process and self._process.poll() is not None:
                with self._lock:
                    self._gateway_state = "error"
                raise LocalAISetupError(
                    "The local model service could not start. Select Retry; details are in runtime.err.log."
                )
            if _reachable(f"{LOCAL_ROUTER_URL}/health/liveliness"):
                self._configure_route()
                with self._lock:
                    self._gateway_state = "running"
                    if voice_ready:
                        self._state = "running"
                    self._detail = self._ready_detail(voice_ready)
                return
            time.sleep(0.5)
        with self._lock:
            self._gateway_state = "error"
        raise LocalAISetupError("Local models did not finish loading within three minutes. Select Retry.")

    def _configure_route(self) -> None:
        """Point the companion at the gateway this launch started (its port is chosen by the launcher)."""
        provider = self.companion.router.settings.model_provider
        if self.mode == "local":
            self._configure_local_route()
            return
        if self.mode == "hosted" and provider == "hosted":
            self.companion.router.configure({
                "router_url": LOCAL_ROUTER_URL,
                "model_provider": "hosted",
                "text_model": HOSTED_MODEL,
                "vision_model": HOSTED_MODEL,
                "transcribe_model": "local-whisper",
                "speech_model": "local-kokoro",
            })
        elif self.mode == "external" and provider == "custom":
            # External mode never started this gateway before, and the launcher
            # picks its port per launch, so the saved :4000 URL was unreachable.
            self.companion.router.configure({"router_url": LOCAL_ROUTER_URL})
        else:
            return
        self.companion.apply_settings()

    def _configure_local_route(self) -> None:
        if self.companion.router.settings.model_provider != "local":
            return
        self.companion.router.configure(
            {
                "router_url": LOCAL_ROUTER_URL,
                "model_provider": "local",
                "text_model": "local-coder",
                "vision_model": "local-coder" if not self._profile or self._profile.get("projector") else "local-no-vision",
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
