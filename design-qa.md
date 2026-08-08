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
| Playable preview | Passed | The right panel loads the installed OpenRA map preview with both spawn points after package validation and cache indexing. |
| Observable generation | Passed | Six live stages report Earth geometry, terrain capture, AI terrain vision, gameplay translation, validation, and ready-to-play state from the asynchronous backend job. |
| Terrain DNA | Passed | Relief, water, urban density, vegetation, and landmarks populate from the returned synthesis and geographic feature counts. |
| Configuration clarity | Passed | Area, map size, mission shape, and translation style use native dropdowns; precise coordinates and seed stay behind Advanced. |
| Layout quality | Passed | The full workbench is centered, unclipped, readable, and preserves the native OpenRA chrome at the tested 2560×1440 viewport and configured UI scale. |
| Failure resilience | Passed | Search, terrain capture, generation, AI analysis, and map indexing errors remain inside the workbench without disrupting the running game. |
| Automated verification | Passed | Engine build, OpenRA mod tests, 23 companion tests, and 13 world-generation tests pass. |

## Final result

Passed. The old form-only studio has been replaced by the proposed visual workbench, with real Earth terrain on the left, a validated playable OpenRA translation on the right, and the entire generation-to-play/editor path kept inside the game.
