# RA2 modern faction art sources

These are original project unit portraits made with the built-in image-generation
tool on 2026-09-03. They are not copied EA/Westwood unit art. The final portraits
are the three `*-portraits-v1.png` files here. Each is a 2×2 atlas, in the unit
order below. Build-button derivatives and 512px faction previews are produced by
`scripts/build-ra2-faction-art.py`.

## Prompt set

Shared prompt: production sidebar portrait atlas for an original Red Alert
2-compatible mod; exact 2×2 contact sheet of four equal edge-to-edge cells; no
borders, gutters, text, flags, insignia or watermarks. Early-2000s RTS illustrated
CG build-button treatment, clear three-quarter views, chunky readable silhouettes,
detailed metal panels, muted military colors, crisp top-left lighting, charcoal
teal background and restrained red player-color strips. Keep the entire vehicle
in its cell with safety padding. Prioritize readability at 60×48 over micro-detail.

- **China:** Qilin low-profile green tracked tank, angular single-cannon turret,
  six wheels/side skirts/rear grilles; Lynx compact tracked recon vehicle with
  autocannon and electro-optical mast; Mantis tracked AA with paired rectangular
  missile pods and upright radar; Cloud dark-slate triangular flying-wing drone.
  Reference: `assets/china-faction/icon-sources/china-unit-cameo-atlas-v1.png`.
- **Iran:** Karrar sand/olive tracked tank with angular turret and roof optics;
  Raad eight-wheel AA truck with paired raised missile boxes and radar;
  Fajr eight-wheel truck with a large tilted grid rocket rack; Mohajer slender
  long-wing reconnaissance/strike drone with twin booms, sensors and wing pods.
- **Turkey:** Bozkir olive tracked tank with angular single-cannon turret;
  Yildirim eight-wheel mobile howitzer; Sancak six-wheel EW/recon truck with a
  rectangular radar panel, antennas and short defensive weapon; Kuzgun slate
  long-wing drone with paired raised tail fins, underbody sensors and pods.
  Reference: `assets/turkey-faction/concept-sources/turkey-roster-concept.png`.

The image tool generated portraits, **not battlefield animation frames**.
Battlefield models come from the existing original China/Iran/Turkey Mesh
geometry in `scripts/*_directional_assets.py`, adapted by
`scripts/ra2_faction_voxels.py`. The Mohajer wing/tail adapter matches the new
portrait's twin-boom silhouette while retaining the original fuselage/materials.

## Lessons carried forward

- Native RA2 VXL/HVA projection and smooth facing changes; no rotated bitmaps
  and no RA1 classic-perspective yaw table.
- Separate hull and turret models; shared origin and real 3D geometry.
- RA2 normal table, exact 16–31 player-remap ramp and a project-owned palette.
- Comparison against locally owned Grizzly/Rhino units at the same camera zoom.
- Bright neutral armor with localized team-color panels, readable wheels/tracks,
  optics, guns/radars and distinct drone silhouettes.
- Native shadows, muzzle effects and falling drone husks. Ground vehicles use
  RA2's normal explosion-on-death behavior, not invented persistent wreck art.
- Power-of-two UI atlases, native 60×48 icons, 512×512 experience previews and
  existing project flags. Do not stretch a square portrait into a wide icon.

The geometry/export code is GPL-3.0-or-later project work. The portraits and
palette are original project presentation assets. No owned `.mix`, `.vxl`,
`.hva`, palette or cameo files extracted for comparison are committed here.
