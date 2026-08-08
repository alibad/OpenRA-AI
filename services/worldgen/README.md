# World-generation service

This service converts a geographic selection into a deterministic mission
package.

Internal stages:

- geographic data acquisition and attribution;
- terrain-image and feature interpretation;
- native OpenRA `ClassicMapGenerator` profile selection;
- OpenRA Terraformer terrain, spawn, resource, and road generation;
- story and Lua mission generation;
- tracked-unit locomotor and spawn-zone validation;
- packaging and manifest generation.

Each stage is independently testable and cacheable.

## Run it

The generator requires Python 3.11+ and a local build of the pinned OpenRA
engine fork. It never calls a hosted build or workflow:

```powershell
python -m pip install -e services/worldgen
openra-ai-worldgen generate --lat 24.7136 --lon 46.6753 --title "Riyadh Crossing" --seed 42
openra-ai-worldgen validate generated/missions/riyadh-crossing-42.oramap
openra-ai-worldgen serve
```

Live generation requests geographic evidence from OpenStreetMap and retains
attribution in the package manifest. The evidence selects native OpenRA
terrain settings; OpenRA itself creates legal tile transitions and checks that
a tracked unit can reach every player spawn. If acquisition is unavailable,
the generator records the degraded source path and uses a conservative native
profile instead of pretending the result is an exact geographic reconstruction.
