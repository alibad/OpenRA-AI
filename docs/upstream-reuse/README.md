# Upstream reuse program

This directory governs the systematic analysis and adaptation of external
OpenRA mods into reusable OpenRA AI components. It is an engineering and
provenance system, not a bulk asset-import directory.

## Rules

1. Pin every upstream repository and record every contributing source path.
2. Treat C# and Lua as GPL-compatible code unless a project states otherwise.
3. Treat YAML as copyrightable mod data whose reuse terms must be confirmed.
4. Treat every sprite, voxel, sound, voice, music track, video, logo, and name as
   blocked until its exact license and author are recorded.
5. Prefer adapting behavior onto original OpenRA AI assets over copying mixed or
   non-commercial content.
6. Keep each component removable and independently gated until it passes lint,
   build, automated gameplay, and live visual validation.
7. Vehicle art is not verified until facing order, fixed pivot, scale, layers,
   palette, and a continuous live turn have been checked against native units.

## Rebuilding the inventory

The source-only checkouts live beside this repository in `../OpenRA-Upstreams`.
They intentionally omit large binary blobs while preserving every Git tree path.

```powershell
./.venv/Scripts/python.exe scripts/openra_upstream_inventory.py
./.venv/Scripts/python.exe scripts/openra_upstream_inventory.py --check
```

The generated Markdown summary is review-oriented. The JSON catalog is the
complete machine-readable inventory containing actors, source lines, traits,
weapons, factions, missions, Lua calls/story-pattern tags, custom C# TraitInfo
classes, and asset paths.

## Using the curated results

- `PORTFOLIO.md` explains the source-by-source decisions and delivery order.
- `roadmap.json` is the prioritized, machine-readable capability queue.
- `components/*.json` records exact provenance, integration files, and evidence
  for each component that enters implementation.
- `component.schema.json` is the contract for those manifests.

Validate pins, catalog freshness, upstream paths, component manifests,
integration paths, and roadmap references with:

```powershell
./.venv/Scripts/python.exe scripts/check_openra_reuse.py
```

Run the complete isolated engine build, RA/map lint, interface checks, inventory
check, and manifest check without touching a running game process with:

```powershell
./scripts/verify_openra_reuse.ps1
```

## Component lifecycle

`discovered` -> `license-review` -> `compatibility-review` -> `adapting` ->
`integrated` -> `verified`

A component can be marked `rejected` at any stage. Rejection is appropriate for
unclear ownership, non-commercial restrictions, incompatible engine-fork
assumptions, duplicated functionality, or gameplay that does not fit the World
War III product direction.
