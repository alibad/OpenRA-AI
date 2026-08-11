# M1A2S directional source prompts

Generated with Codex's built-in OpenAI image-generation tool on 2026-08-11.
These sheets are art-direction and geometry studies. The runtime SHP is rendered
deterministically from `scripts/red_sea_directional_vehicle.py` so every one of
the 32 hull and 32 turret facings has a stable camera, pivot, scale, and order.

## Hull study

```text
Use case: stylized-concept
Asset type: production source board for an OpenRA / classic Red Alert vehicle sprite
Input images: Image 1 is the M1A2S Abrams identity and material reference; preserve its hull proportions, tan armor, track layout, engine deck, front glacis, and surface details. Image 2 is the exact style, camera, scale behavior, and directional-pose reference from the stock OpenRA 2TNK; match its fixed orthographic isometric camera and genuinely redrawn directional geometry.
Primary request: Create a precise 4 by 4 sprite board containing exactly sixteen separate views of the SAME turretless M1A2S hull, evenly rotating clockwise through a full 360 degrees in 22.5-degree steps. Top-left is north-facing; continue left-to-right, top-to-bottom. Each view must be a true isometric render from a fixed camera elevation, not a flat top-down image rotated in 2D. Side facings must reveal vertical side armor and track depth; front and rear facings must show the correct glacis or engine/rear geometry. Lighting direction and vehicle scale must remain fixed across all sixteen cells.
Scene/backdrop: perfectly flat solid #ff00ff chroma-key background in every cell, no grid lines, no labels, no borders, no scenery.
Style/medium: crisp hand-painted 1990s RTS pixel-art source, readable after reduction to a 40x40 OpenRA SHP frame, restrained detail, hard silhouettes.
Composition/framing: exact 4x4 grid, one centered hull per equal-size cell, identical anchor point and generous padding, no overlaps.
Lighting/mood: fixed upper-left desert sunlight, consistent cast/contact shadow in every direction.
Constraints: hull only; remove the turret, cannon, muzzle flash, text, labels, watermark, UI, cell dividers. Exactly sixteen views, same vehicle identity and size. The object must never touch a cell boundary.
Avoid: rotating-cardboard effect, top-down-only view, inconsistent camera angle, inconsistent hull length, missing tracks, duplicated directions, extra vehicles, perspective camera distortion.
```

## Turret study

```text
Use case: stylized-concept
Asset type: production source board for the independently rotating turret sequence of an OpenRA / classic Red Alert vehicle sprite
Input images: Image 1 defines the M1A2S turret, cannon, hatches, smoke launchers, tan material, and details. Image 2 is the matching sixteen-view turretless hull board and defines the exact 4x4 cell layout, rotation order, camera elevation, lighting, scale, and anchor. Image 3 is the stock OpenRA 2TNK directional sprite reference and defines how isolated turret sprites are genuinely redrawn at each direction.
Primary request: Create a precise 4 by 4 sprite board containing exactly sixteen isolated views of the SAME M1A2S turret and cannon assembly, evenly rotating clockwise through a full 360 degrees in 22.5-degree steps. Top-left is north-facing; continue left-to-right, top-to-bottom. Every turret must use the same fixed orthographic isometric camera elevation as Image 2. The cannon must point in the turret's current direction, with correct foreshortening: nearly hidden/short when aimed toward or away from the camera, longest in side-facing views. Turret side armor, roof, rear bustle, hatches, and smoke launchers must change visibility naturally per angle.
Scene/backdrop: perfectly flat solid #ff00ff chroma-key background in every cell, no grid lines, no labels, no borders, no scenery.
Style/medium: crisp hand-painted 1990s RTS pixel-art source, designed to remain readable after reduction to a 40x40 SHP frame.
Composition/framing: exact 4x4 grid matching Image 2, one centered isolated turret per equal cell, identical pivot/anchor point and generous padding. No hull and no tracks.
Lighting/mood: fixed upper-left desert sunlight, consistent across all sixteen directions. No separate cast shadow; the turret will be composited over a hull.
Constraints: isolated turret plus cannon only; exactly sixteen views; same turret identity and scale; no hull, tracks, muzzle flash, text, watermark, UI, labels, cell dividers. Nothing may touch a cell boundary.
Avoid: flat 2D rotation, rotating-cardboard effect, inconsistent camera height, duplicated directions, inconsistent barrel length unrelated to foreshortening, bent cannon, extra vehicles, perspective distortion.
```
