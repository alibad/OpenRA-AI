# Model routing

## Current routes

OpenRA AI talks only to a private OpenAI-compatible AI layer. The application
`.env` contains route names and a loopback URL, but no provider credential.
The router owns the provider key and maps capabilities to backends:

- `gpt-5.5` writes a single short response from a compact game snapshot;
- `openai-transcribe` turns a push-to-talk WAV into the player question;
- `openai-tts` returns interruptible WAV speech.

The text route uses low reasoning effort and a strict one-sentence system
instruction. Deterministic code—not the model—decides whether an observation
is salient enough to speak. If the route is unavailable, critical events retain
a deterministic fallback line and player questions report degraded status.

## Data boundary

The model can receive cash, power, production, owned assets, explored percent,
and enemies already visible to the local player. It does not receive hidden
actors, unrestricted map state, a continuous frame stream, credentials, or a
game-command tool.

## Moving local

The public contracts do not name a provider. A future local rollout changes
AI-layer routes to local text, speech-recognition, and speech-synthesis
backends, then compares latency and quality against recorded fog-respecting
snapshots. The engine, companion API, interruption model, and UI remain the
same.
