# Design QA: Provider-first AI settings

Reference: `codex-clipboard-ee0dabae-4096-4b5b-abf7-eaea01ca9835.png`

Verified implementation captures:

- `openra-provider-settings-live-final.png` — hosted provider flow
- `openra-provider-settings-custom.png` — custom endpoint flow

## Checklist

| Check | Result | Notes |
| --- | --- | --- |
| Provider-first hierarchy | Passed | The first control is a provider dropdown with OpenAI, Anthropic/Claude, Google/Gemini, local, and custom choices. |
| Hosted model selection | Passed | Companion and map-understanding models use dropdowns populated from the AI-layer catalogue. |
| Hosted URL removal | Passed | OpenAI, Claude, and Gemini do not show or request an endpoint URL. The screen explains that credentials and routing are managed by the AI layer. |
| Local model selection | Passed | Models registered by the local AI layer appear under a dedicated local provider without exposing internal service URLs. |
| Custom endpoint escape hatch | Passed | Selecting Custom endpoint reveals the OpenAI-compatible URL and explicit companion/map model ID fields. |
| Voice and listening setup | Passed | Listening model, speech model, and voice personality are dropdowns. |
| Layout and action visibility | Passed | Cost estimate, Apply Now, Test AI + Voice, Refresh Costs, Reset, and Back remain visible in the normal viewport. |
| Native visual consistency | Passed | Controls reuse OpenRA settings chrome, typography, spacing, dropdowns, and button styles. |
| Runtime load and stability | Passed | The native screen loaded against the live companion catalogue without a settings crash. |
| Automated verification | Passed | Companion tests, engine build, and OpenRA mod tests pass. |

## Final result

Passed. The implementation resolves the raw-route-field experience in the reference and keeps endpoint configuration limited to the custom-provider path.

---

# Design QA: Earth-to-Battlefield Workbench

Reference: `codex-clipboard-cc19f9e3-cee2-443b-96fc-5689e9d6708c.png`

Verified implementation captures:

- `openra-earth-workbench-live-v5.png` — native initial state
- `openra-earth-workbench-generated-v2.png` — generated and validated battlefield state
- `openra-earth-workbench-design-comparison.png` — side-by-side reference comparison

## Checklist

| Check | Result | Notes |
| --- | --- | --- |
| Single native journey | Passed | World Tools opens one in-game workbench. A generated map can be played or continued directly into the native editor from the same surface. |
| Reference structure | Passed | The implementation matches the proposed split Earth/translation workbench, mission controls, terrain analysis, progress, and bottom action hierarchy. |
| Real Earth interaction | Passed | The left panel renders a free OpenTopoMap/OpenStreetMap terrain view, selection center, area radius, search, and click-to-recenter behavior. |
| Honest AI input | Passed | The exact terrain view shown to the player is passed through the AI layer as multimodal image content during generation. |
| Playable preview | Passed | The right panel loads OpenRA's own rendered map preview with both spawn points after package validation and cache indexing. |
| Observable generation | Passed | Six live stages report Earth geometry, terrain capture, AI terrain vision, gameplay translation, validation, and ready-to-play state from the asynchronous backend job. |
| Terrain DNA | Passed | Relief, water, urban density, vegetation, and landmarks populate from the returned synthesis and geographic feature counts. |
| Configuration clarity | Passed | Area, map size, mission shape, and translation style use native dropdowns; precise coordinates and seed stay behind Advanced. |
| Layout quality | Passed | The full workbench is centered, unclipped, readable, and preserves the native OpenRA chrome at the tested 2560×1440 viewport and configured UI scale. |
| Failure resilience | Passed | Search, terrain capture, generation, AI analysis, and map indexing errors remain inside the workbench without disrupting the running game. |
| Native map construction | Passed | Earth evidence selects a Red Alert tileset and ClassicMapGenerator profile; OpenRA Terraformer owns transitions, roads, passages, spawns, resources, and scenery. |
| Unit passability gate | Passed | A map is rejected unless the real Red Alert tracked locomotor reaches every spawn and each spawn retains a usable base zone. |
| Automated verification | Passed | Engine build, OpenRA map lint, 23 companion tests, and 14 world-generation tests pass. |

## Final result

Passed. The old form-only studio has been replaced by the proposed visual workbench, with real Earth terrain on the left, a validated playable OpenRA translation on the right, and the entire generation-to-play/editor path kept inside the game.

## Satellite reconnaissance iteration (2026-08-09)

Source of truth:

- `C:/Users/Admin/.codex/generated_images/019fbcef-7ff1-77d3-bd57-618d3542810f/exec-484fa1ef-4e80-4010-b6c5-8586cdd24c20.png`

Verified implementation:

- `artifacts/earth-workbench-satellite-generated.png` — 2560×1440 generated and validated state
- `artifacts/earth-workbench-design-comparison.png` — normalized reference/implementation comparison input

Iteration history:

1. The first satellite build (`artifacts/earth-workbench-world-tools-3.png`) overflowed the viewport under 150% Windows display scaling. This was a P1 layout defect.
2. The workbench now converts the physical `WINDOW_*` dimensions into UI-scaled bounds, keeps all controls visible, and preserves the reference's split reconnaissance/translation hierarchy.
3. A live Riyadh generation populated all five Earth-detection cards, produced the native map preview, and reached the validated/ready state.

| Check | Result | Notes |
| --- | --- | --- |
| Satellite source | Passed | The default source is EOX Sentinel-2 Cloudless 2025, with its attribution visible in the Earth pane. |
| Terrain alternative | Passed | The source dropdown can switch to OpenTopoMap terrain imagery without leaving the game. |
| Exact-image grounding | Passed | The PNG displayed in the reconnaissance pane is the same image embedded in the package and sent to the AI terrain route. |
| Detected-from-Earth quality | Passed | Relief, water, built area, vegetation, and landmarks use scan cards with values, confidence bars, concise details, and a provenance/status header. |
| Truthful playable preview | Passed | The right pane renders the generated OpenRA map rather than an illustrative mock. Spawn points and validated status are visible. |
| Native playability | Passed | The output uses `ClassicMapGenerator`; tracked locomotor reached both spawns, 9,001 cells, and 169 cells in the smallest spawn zone. |
| Layout fidelity | Passed | Search, dual visual panes, controls, analysis, pipeline, and bottom actions match the reference structure with no clipping at 2560×1440. |
| Remaining differences | Accepted | The reference's isometric battlefield art is aspirational. The product deliberately shows OpenRA's real generated-map preview so the UI never promises terrain that was not built. |

### Final result

passed

## Tactical scale and zoom iteration (2026-08-09)

Sources of truth:

- `C:/Users/Admin/AppData/Local/Temp/codex-clipboard-8300c930-515c-4ad6-ae80-efbaad0941cb.png` - reported fixed-scale workbench and physical-scale concern
- `artifacts/qa/earth-workbench-fixed-internal.png` - native OpenRA renderer capture after the responsive-layout and zoom revision
- `artifacts/qa/earth-workbench-comparison-final.png` - same-state reference and implementation comparison input
- `artifacts/qa/riyadh-map-buildings.png` - close-range map-and-buildings source verification

Iteration history:

1. The former 2 km-radius default represented roughly 42 metres per 96x96 cell, which was too coarse for tanks, streets, and individual buildings. The default battlefield is now 1 km across (500 m radius), or approximately 10.4 metres per cell.
2. Earth reconnaissance now has bounded **Closer**, **Wider**, and **Fit Area** controls plus mouse-wheel zoom. Reconnaissance can move independently from a 500 m tactical view to an 8 km context view without silently changing the battlefield footprint.
3. The selected battlefield is drawn as a scaled circle inside the current Earth view. The UI reports both the battlefield width/cell scale and the current source-view width so users can distinguish game scale from reconnaissance zoom.
4. The close-range **Map + buildings** source exposes OpenStreetMap building footprints and street geometry. Real building ways are also included in the geographic feature query used by generation.
5. The runtime layout now sizes against the DPI-adjusted UI viewport but centers in renderer coordinates, preserving equal opposing margins across the tested high-DPI resolution.

| Fidelity surface | Result | Notes |
| --- | --- | --- |
| Responsive centering | Passed | The complete workbench and footer are centered and visible in the native renderer capture at the reported resolution and Windows scaling. |
| Zoom interaction | Passed | Buttons, mouse wheel, bounded zoom levels, and Fit Area are connected to fresh Earth-preview requests. |
| Physical scale | Passed | The default 1 km-wide battlefield maps to 10.4 m/cell at 96x96; larger presets are explicitly labelled as compressed. |
| Building visibility | Passed | Close map view shows individual building footprints and roads; the satellite source remains available for visual texture and land-cover evidence. |
| Scale honesty | Passed | Battlefield footprint, source-view width, approximate source resolution, and compressed presets are disclosed in the UI. |
| Visual comparison | Passed | Equal-margin centering, zoom affordances, scale readout, and full action visibility were checked in the combined comparison image. |
| Defect audit | Passed | No P0, P1, or P2 layout defect remains in the verified initial state. |

### Final result

passed

## Vision-grounded blueprint iteration (2026-08-09)

Source visual truth:

- `artifacts/design-variants/variant-2.png` - selected guided-builder direction
- `artifacts/design-variants/variant-3.png` - selected tactical-workbench direction
- `C:/Users/Admin/.codex/generated_images/019fbcef-7ff1-77d3-bd57-618d3542810f/exec-484fa1ef-4e80-4010-b6c5-8586cdd24c20.png` - full Earth-to-Battlefield composition

Rendered implementation:

- `artifacts/earth-workbench-blueprint-v2.png` - 2560x1440 native OpenRA capture at 150% Windows UI scale
- `artifacts/earth-workbench-vision-comparison-v2.png` - normalized full-view comparison containing both selected directions, the prior implementation, and the revision
- `artifacts/earth-workbench-blueprint-focus-comparison.png` - focused guided-builder/mission-blueprint comparison

State: initial Earth source loaded, mission editable, generation not started. The before and after OpenRA captures use the same 2560x1440 game viewport, map, location, imagery source, and empty-generation state. The 540x540 direction images are visual-concept crops and were contained rather than stretched for comparison.

### Comparison history

1. The prior revision was centered in the captured runtime but remained a dual-pane form with only a thin four-label strip and two renamed buttons. This was a P1 fidelity and product-hierarchy miss: the selected guided-builder and tactical-workbench directions were not visible in the experience.
2. The workbench was rebuilt around three primary regions: live Earth reconnaissance, a central mission blueprint, and the truthful playable OpenRA translation. Mission shaping moved into the blueprint rather than remaining a detached form row.
3. Translation checks now expose Earth evidence, route-safety ownership, and design intent. Terrain cards explain how each signal changes play, and the six-stage pipeline is presented as an explicit build board.
4. The window is reflowed from the effective UI resolution on every open. The post-fix capture shows equal opposing margins with the complete frame, footer, and actions visible.

### Fidelity surfaces

| Surface | Result | Evidence |
| --- | --- | --- |
| Fonts and typography | Passed | Native Red Alert fonts remain crisp; the mission headline, field labels, status values, and pipeline stages establish the same dense builder hierarchy as the selected directions. |
| Spacing and layout rhythm | Passed | The source/blueprint/result three-column body is balanced, the bottom analysis/build board aligns to it, and no panel or persistent action is clipped. |
| Colors and tokens | Passed | Native chrome is preserved while green, amber, red, white, and muted gray communicate complete, active, failed, ready, and pending states. |
| Image quality and asset fidelity | Passed | The left pane uses the real satellite raster at native quality; the right pane remains reserved for the real generated OpenRA preview rather than illustrative placeholder art. |
| Copy and content | Passed | Labels describe the actual journey and ownership: Earth evidence, route safety, design intent, terrain effects, generation stages, and play/editor outcomes. |

### Findings

- No actionable P0, P1, or P2 visual differences remain in the verified initial state.
- P3 accepted difference: the concept crops use a separate dark visual system and pictographic decoration. The implementation deliberately reuses OpenRA's native Red Alert chrome and does not manufacture substitute icons.

### Final result

passed

## Centered guided-workbench iteration (2026-08-09)

Sources of truth:

- `C:/Users/Admin/AppData/Local/Temp/codex-clipboard-a0062d2b-8f6c-48a2-8936-5ce4ea73aabd.png` - reported upper-left/clipped state
- `C:/Users/Admin/.codex/generated_images/019fbcef-7ff1-77d3-bd57-618d3542810f/exec-484fa1ef-4e80-4010-b6c5-8586cdd24c20.png` - full-workbench visual direction
- `C:/Users/Admin/AppData/Local/Temp/codex-clipboard-06aec082-942e-4aee-a2bc-24ec8681e01c.png` - workflow and builder variations

Verified implementation:

- `artifacts/earth-workbench-centered-guided-v2.png` - 2560x1440 native initial state
- `artifacts/earth-workbench-next-level-comparison.png` - combined reference, variation, before, and after comparison input

Iteration history:

1. The prior layout mixed physical render dimensions with UI-scaled placement. At 150% Windows scaling this anchored the workbench in the upper-left and could push part of it beyond the usable viewport. This was a P1 defect.
2. The workbench now reflows its complete widget tree against the effective UI resolution, occupies 94% x 92% of the viewport, and centers with equal margins.
3. The three reference variations were consolidated into one native journey: a persistent four-stage guide, a large Earth/translation comparison, visible mission-shaping controls, a terrain-intelligence deck, and a live validation pipeline.
4. The previously preferred generation modes are now direct segmented choices: **Earth + Balance** and **Creative Remix**. Reality-first remains available to backend tooling but is not promoted in this player flow.

| Fidelity surface | Result | Notes |
| --- | --- | --- |
| Workflow correctness | Passed | Pin Earth, shape mission, build and validate, then play or edit are explicit and ordered. |
| Information hierarchy | Passed | Satellite reconnaissance and playable translation dominate; mission choices, Earth evidence, pipeline, and actions follow in task order. |
| Readability and spacing | Passed | No text, controls, panel borders, or bottom actions are clipped at the tested 2560x1440 viewport and 150% UI scale. |
| Visual consistency | Passed | The redesign stays inside Red Alert's native chrome, typography, field, dropdown, button, and progress vocabulary. |
| Interaction and state | Passed | Search, imagery source, mission shape, map scale, translation mode, Advanced, generation, play, and editor affordances retain real native handlers and truthful enabled states. |
| Comparison fidelity | Passed | The final screen preserves the reference's nearly full-screen workbench and split source/result composition while showing real satellite evidence and a truthful empty translation state before generation. |
| Defect audit | Passed | No P0, P1, or P2 visual or interaction defects remain in the verified initial state. |

### Final result

passed
