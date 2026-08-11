# Model routing

## Current routes

OpenRA AI talks only to a private OpenAI-compatible AI layer. The application
`.env` contains route names and a loopback URL, but no provider credential.
The router maps capabilities to local backends by default:

- `local-coder` writes text responses and interprets proposed actions with tool calling;
- `local-whisper` turns a push-to-talk WAV into the player question;
- `local-kokoro` returns interruptible WAV speech.

The autonomous headless game agent uses the Agents SDK against the same
BeTenshi router so it can call the local gameplay MCP server. Local mode pins
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

## Local operation

The game-facing contracts do not name a provider. The local text,
speech-recognition, and speech-synthesis routes can be changed in BeTenshi
without changing the engine, companion API, interruption model, or UI.
