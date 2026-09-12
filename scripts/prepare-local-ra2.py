"""Cache the integrated RA2 data for a canonical source checkout, without replacing binaries."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_ra2", ROOT / "scripts/prepare-ra2.py")
prepare_ra2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_ra2)


def prepare_local(engine: Path) -> Path:
    engine = engine.resolve()
    digest = hashlib.sha256()
    inputs = [ROOT / "scripts/prepare-ra2.py", ROOT / "scripts/build-ra2-preview.py", Path(__file__)]
    inputs += sorted((ROOT / "apps/installer/ra2").rglob("*"))
    inputs += sorted((engine / "mods/ra/chrome").glob("*.yaml"))
    inputs += sorted((engine / "mods/ra/bits").glob("*.wav"))
    inputs += [engine / "mods/ra/uibits/glyphs-redsea.png", engine / "mods/ts/uibits/glyphs.png",
               engine / "mods/ra/uibits/experience-previews/unit-composition-doctrine-ai.png"]
    for path in inputs:
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    cache = engine / "Support/IntegratedGames"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / digest.hexdigest()[:20]
    if not (target / "RA2-BUILD.json").is_file():
        # Never overwrite user edits or an incomplete previous stage.
        stage = Path(tempfile.mkdtemp(prefix="stage-", dir=cache))
        version = (engine / "VERSION").read_text(encoding="utf-8").strip()
        prepare_ra2.prepare(stage, engine / "bin", version, True, "win-x64", engine, True)
        stage.rename(target)
    return target / "mods"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    args = parser.parse_args()
    print(prepare_local(args.engine))
