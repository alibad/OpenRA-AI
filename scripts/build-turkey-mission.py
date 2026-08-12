"""Package the deterministic Straits Shield mission."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"missions"/"turkey-faction"/"straits-shield"
TERRAIN=ROOT/"engine"/"openra"/"mods"/"ra"/"maps"/"shuriken-island"
OUTPUT=ROOT/"generated"/"missions"/"straits-shield-2026.oramap"
INSTALL=ROOT/"engine"/"openra"/"mods"/"ra"/"maps"/"straits-shield-2026.oramap"
FIXED_TIME=(2026,8,12,0,0,0)
TEXT_SUFFIXES={".ftl",".json",".lua",".md",".txt",".yaml",".yml"}


def info(name: str) -> zipfile.ZipInfo:
	result=zipfile.ZipInfo(name,FIXED_TIME); result.compress_type=zipfile.ZIP_DEFLATED; result.external_attr=0o644<<16; return result


def source_bytes(path: Path) -> bytes:
	data=path.read_bytes()
	if path.suffix.lower() in TEXT_SUFFIXES:
		return data.replace(b"\r\n",b"\n").replace(b"\r",b"\n")
	return data


def main() -> int:
	files={path.name:source_bytes(path) for path in sorted(SOURCE.iterdir()) if path.is_file() and path.name not in {"README.md"}}
	files["map.bin"]=(TERRAIN/"map.bin").read_bytes(); files["map.png"]=(TERRAIN/"map.png").read_bytes()
	manifest={
		"schema":"openra-ai.scripted-mission/v1",
		"id":"straits-shield-2026",
		"research_cutoff":"2026-08-12",
		"scenario":"Fictional island-strait combined-arms operation; no real leader, operation, location, or recent attack.",
		"features":["player construction and harvesting","complete Turkey tech progression","drone designation","mechanized infantry","amphibious landings","air rearming","naval-yard construction","surface warfare","bilingual Turkish and English radio","difficulty-scaled attacks"],
		"terrain_source":"OpenRA Shuriken Island map.bin by Janitor and Luftwaffe",
		"files":{name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())},
	}
	files["turkey-mission-manifest.json"]=json.dumps(manifest,ensure_ascii=False,indent=2).encode("utf-8")+b"\n"
	OUTPUT.parent.mkdir(parents=True,exist_ok=True)
	with zipfile.ZipFile(OUTPUT,"w") as archive:
		for name,data in sorted(files.items()): archive.writestr(info(name),data)
	INSTALL.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(OUTPUT,INSTALL)
	print(f"Mission: {OUTPUT}"); print(f"Installed: {INSTALL}"); print(f"SHA256: {hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}")
	return 0


if __name__=="__main__": raise SystemExit(main())
