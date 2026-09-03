from __future__ import annotations

import ctypes
import os
import platform
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


GIB = 1024 ** 3


@dataclass(frozen=True)
class Hardware:
    total_bytes: int = 0
    available_bytes: int = 0
    cores: int = 2
    accelerated: bool = False

    @classmethod
    def detect(cls) -> "Hardware":
        total = available = 0
        try:
            if sys.platform == "darwin":
                total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=2))
                stats = subprocess.check_output(["vm_stat"], text=True, timeout=2)
                page_size = int(re.search(r"page size of (\d+) bytes", stats)[1])
                pages = sum(int(value) for value in re.findall(
                    r"Pages (?:free|inactive|speculative):\s+(\d+)", stats))
                available = pages * page_size
            elif os.name == "nt":
                class MemoryStatus(ctypes.Structure):
                    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                        (name, ctypes.c_ulonglong) for name in
                        ("total", "available", "page", "free_page", "virtual", "free_virtual", "extended")
                    ]
                status = MemoryStatus()
                status.length = ctypes.sizeof(status)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    total, available = status.total, status.available
            else:
                memory = Path("/proc/meminfo").read_text()
                total = int(re.search(r"MemTotal:\s+(\d+)", memory)[1]) * 1024
                available = int(re.search(r"MemAvailable:\s+(\d+)", memory)[1]) * 1024
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            pass
        return cls(total, available, os.cpu_count() or 2,
                   sys.platform == "darwin" and platform.machine() == "arm64")

    @property
    def model_budget_bytes(self) -> int:
        return max(0, min(self.total_bytes - 4 * GIB, self.available_bytes - 2 * GIB, 8 * GIB))


def choose_profile(manifest: dict, hardware: Hardware, preference: str = "auto") -> dict:
    profiles = manifest.get("model_profiles", [])
    if not profiles:
        return {}
    eligible = [profile for profile in profiles if profile.get("validated") is True]
    if not eligible:
        raise ValueError("The model catalogue has no validated profiles")
    for profile in eligible:
        if profile["id"] == preference:
            if hardware.total_bytes and profile["memory_bytes"] > hardware.model_budget_bytes:
                raise ValueError("That AI profile leaves too little memory for the game. Choose Automatic.")
            return dict(profile)
    if preference not in {"auto", "manual"}:
        raise ValueError("Unknown local AI profile")
    compatible = [profile for profile in eligible
                  if profile["memory_bytes"] <= hardware.model_budget_bytes
                  and (not profile.get("prefers_acceleration") or hardware.accelerated)]
    if compatible:
        return dict(max(compatible, key=lambda profile: profile["priority"]))
    smallest = min(eligible, key=lambda profile: profile["memory_bytes"])
    if hardware.total_bytes and smallest["memory_bytes"] > hardware.model_budget_bytes:
        raise ValueError("Not enough free memory for local AI while keeping the game responsive. Close other apps and relaunch.")
    return dict(smallest)


def selected_components(manifest: dict, profile: dict) -> list[dict]:
    if not profile:
        return manifest["components"]
    components = {entry["id"]: entry for entry in
                  [*manifest["components"], *manifest.get("optional_components", [])]}
    return [components[component_id] for component_id in profile["components"]]


def selection_status(profile: dict, hardware: Hardware, preference: str) -> dict:
    return {
        "preference": preference,
        "profile": profile.get("id", "recommended"),
        "label": profile.get("label", "On-device AI"),
        "model": profile.get("model_name", "Qwen3-VL 2B"),
        "vision": bool(profile.get("projector")),
        "hardware": asdict(hardware),
        "reason": ("Selected to leave memory and CPU capacity for the game."
                   if preference == "auto" else "Your selected profile; changes take effect next launch."),
        "catalogue_policy": "Only tested, checksum-pinned releases; no automatic downloads or model swaps during a match.",
    }


def validate_profiles(manifest: dict) -> None:
    entries = [*manifest["components"], *manifest.get("optional_components", [])]
    ids = {entry["id"] for entry in entries}
    if len(ids) != len(entries) or len({entry["destination"] for entry in entries}) != len(entries):
        raise ValueError("Duplicate model catalogue components")
    seen = set()
    for profile in manifest.get("model_profiles", []):
        if profile["id"] in seen or not profile["components"] or not set(profile["components"]) <= ids:
            raise ValueError("Invalid model profile component references")
        seen.add(profile["id"])
        destinations = {entry["destination"] for entry in entries if entry["id"] in profile["components"]}
        if profile["model"] not in destinations or (profile.get("projector") and profile["projector"] not in destinations):
            raise ValueError("Invalid model profile paths")
        if not 512 <= profile["context_length"] <= 8192 or profile["memory_bytes"] <= 0:
            raise ValueError("Invalid model profile resource budget")
