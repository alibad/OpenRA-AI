"""Install the checksum-pinned Windows model/runtime payload without overwriting a prior install."""
import json
from pathlib import Path
import shutil
import tempfile

import ai_pack


def install(root: Path) -> Path:
    destination = root / "ai"
    lock = ai_pack.load_lock(root / "packaging/ai-pack.lock.json")
    if (destination / "pack.json").is_file():
        for component in lock["components"]:
            ai_pack.verify_component(destination / component["destination"], component)
        return destination
    if destination.exists():
        raise ValueError(f"Incomplete AI install preserved at {destination}; move it aside before retrying.")
    (root / "artifacts").mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="local-ai-", dir=root / "artifacts"))
    for component in lock["components"]:
        source = ai_pack.download_component(ai_pack.DEFAULT_CACHE, component)
        target = stage / component["destination"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    runtime_lock = json.loads((root / "packaging/ai-runtime.lock.json").read_text(encoding="utf-8"))
    runtimes = runtime_lock["targets"]["windows-x64"]["components"]
    for component in runtimes:
        source = ai_pack.download_component(ai_pack.DEFAULT_CACHE, component)
        ai_pack.extract_runtime(source, stage / component["destination"], component)
    (stage / "pack.json").write_text(json.dumps({"pack_version": lock["pack_version"], "components": lock["components"], "runtimes": runtimes}), encoding="utf-8")
    stage.rename(destination)
    return destination


if __name__ == "__main__":
    print(install(Path(__file__).resolve().parents[1]))
