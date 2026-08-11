# Jizan Corridor mission source

This directory contains the authored source for the Red Sea 2026 vertical-slice
mission. `map.bin` and `map.png` are derived from the deterministic geographic
package generated with seed `20260811`; the YAML, Lua, Fluent, voices, actors,
and objectives are authored gameplay content.

Build the distributable package with:

```powershell
scripts\build-red-sea-mission.ps1
```

The factual cutoff is 2026-08-11. Force composition, routes, positions, timing,
and outcomes are fictional gameplay abstractions.
