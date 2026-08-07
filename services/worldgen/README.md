# World-generation service

This service converts a geographic selection into a deterministic mission
package.

Internal stages:

- geographic data acquisition and attribution;
- projection and feature simplification;
- OpenRA terrain compilation;
- spawn, resource, and objective design;
- story and Lua mission generation;
- playability validation and repair;
- packaging and manifest generation.

Each stage is independently testable and cacheable.

## Run it

The generator has no runtime dependencies outside Python 3.11+:

```powershell
python -m pip install -e services/worldgen
openra-ai-worldgen generate --lat 24.7136 --lon 46.6753 --title "Riyadh Crossing" --seed 42
openra-ai-worldgen validate generated/missions/riyadh-crossing-42.oramap
openra-ai-worldgen serve
```

Live generation requests roads and waterways from OpenStreetMap's Overpass
API and retains attribution in the package manifest. If acquisition is
unavailable, the generator emits a clearly marked deterministic fallback map
instead of failing or pretending the synthetic terrain came from real data.
