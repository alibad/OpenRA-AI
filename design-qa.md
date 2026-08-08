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
