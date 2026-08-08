# Companion service

The companion service turns relevant game context and player speech into short,
interruptible responses.

It owns relevance scoring, cooldowns, deduplication, conversation state,
transcription, speech playback coordination, cancellation, and private AI-layer
routing. OpenAI is the initial inference backend; local models can replace it
without changing the game-facing contract.

The initial companion is observation-only and cannot issue game orders.

## Run it

The OpenRA fork publishes a read-only, fog-respecting snapshot on port 9998
when launched with `OPENRA_AI_COMPANION=1`. It does not pause the match or
accept game commands.

```powershell
python -m pip install -e "services/companion[voice]"
$env:OPENRA_AI_COMPANION="1"
openra-ai-companion watch --speak --voice-hotkeys
```

On Windows, hold `Ctrl+Space` for push-to-talk, press `Ctrl+Shift+M` to mute, and press `Ctrl+Shift+A` to
disable or enable the companion. The launcher supplies the OpenRA process ID so
the watcher shuts down with the game.

For local application integration, run `openra-ai-companion serve`. Its small
HTTP API supports snapshot observation, player questions, transcription,
speech, mute/disable controls, notification priority, session cost estimates,
and immediate interruption. OpenRA's native AI settings tab uses `/v1/state`,
`/v1/usage`, and the diagnostic routes; users do not need the HTTP console. All model traffic
uses the named AI-layer routes in the project `.env`; provider keys stay in
the router and are never copied into this repository.
