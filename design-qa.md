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
