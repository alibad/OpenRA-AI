# Model routing

## Automatic selection

Mac local setup defaults to **Automatic — recommended**. A committed catalogue
inside `packaging/ai-pack.lock.json` selects only explicitly validated profiles.
It reserves 4 GiB of total memory and 2 GiB of currently available memory for
the game/OS, caps the model budget at 8 GiB, and limits inference to four CPU
threads and one request slot. Selection happens once at companion launch.
Changing the preference applies on the next launch, not during a match.

The initial catalogue has two profiles using the same pinned Qwen3-VL 2B model:

- Balanced: approximately 1.82 GB, including the image projector.
- Lightweight: approximately 1.38 GB, skipping image processing and relying on
  structured battlefield state. Preferred on CPU-only and memory-constrained
  machines. Unknown hardware also gets this conservative default.

Both include Whisper base.en (English transcription) and Kokoro spoken replies.
Voice is not assumed to be supported by a detected chat model. The game shows
download/model readiness separately from microphone permission and on-demand
speech loading. Legacy `local-small` is not offered as an installed model.

Advanced settings can explicitly detect an LM Studio server on loopback port
1234. Discovery uses its reported tool/vision capabilities and size, preferring
an already loaded model within the memory budget. This fills a proposed custom
configuration; the player must select **Apply Now**. It never starts LM Studio,
downloads models, or changes the live configuration by itself. Token-protected
discovery is not supported yet. Local speech stays on the bundled gateway.

Catalogue updates are deliberately reviewed and shipped with an app update;
there is no unverified internet `latest` alias or background model upgrade.
Maintainers must pin a candidate's exact revision, size, and SHA-256, verify
runtime/license compatibility, and run `scripts/validate-local-model.py`
against an isolated server plus the companion guardrail tests before promotion.
The focused prompt check is a regression gate, not a general model benchmark.
Qwen3.5 0.8B was evaluated on 2026-09-02 and rejected after malformed and
disallowed command responses; it is not part of the downloadable catalogue.

## Current routes

OpenRA AI talks to the bundled loopback gateway at `http://127.0.0.1:4000`.
The gateway has two explicit modes. **Local** starts the models and CPU
inference runtimes from the installed target AI pack. **External** forwards the
same OpenAI-compatible contracts to the endpoint chosen during setup. The game
itself receives route names and the loopback URL, never the provider key.

Local mode maps capabilities to these bundled routes:

- `local-coder` writes text responses and interprets proposed actions with tool calling;
- `local-whisper` turns a push-to-talk WAV into the player question;
- `local-kokoro` returns interruptible WAV speech.

The autonomous headless game agent uses the Agents SDK against the same
loopback gateway so it can call the local gameplay MCP server. Local mode pins
the `local-coder` route, disables SDK tracing, and never loads a hosted-provider
credential or silently falls back to a hosted model.

The text route uses low reasoning effort and a strict one-sentence system
instruction. Deterministic code—not the model—decides whether an observation
is salient enough to speak. Persistent economy, power, production, and damage
alerts are also worded locally and emit only when the condition begins. If a
route is unavailable, critical events retain a deterministic fallback line and
player questions report degraded status.

## Data boundary

The model can receive cash, power, production, owned assets, explored percent,
and enemies already visible to the local player. It does not receive hidden
actors, unrestricted map state, a continuous frame stream, credentials, or a
game-command tool.

## Installation and provider keys

The guided Windows installer selects Local AI by default. It downloads the
matching checksum-pinned pack, verifies it before extraction, and configures
the loopback gateway. The pack remains a separate release asset so portable
users can install it manually and repeat installs can reuse a cached download.

Choosing External during setup avoids the model download. The endpoint can be
a hosted service or an existing local OpenAI-compatible server. A supplied key
is encrypted with Windows DPAPI for the current user and stored outside the
installation under `%APPDATA%/OpenRA-AI/provider.json`. Local endpoints may
leave the key blank.

The game-facing contracts do not name a provider, so text, vision,
speech-recognition, and speech-synthesis backends can change without changing
the engine, companion API, interruption model, or UI. External endpoints must
implement the capabilities the player enables; unsupported voice routes fail
softly while the game and deterministic alerts continue.
