# Companion service

The companion service turns relevant game context and player speech into short,
interruptible responses.

It owns relevance scoring, cooldowns, deduplication, conversation state,
transcription, speech playback coordination, cancellation, and BeTenshi
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
openra-ai-companion watch --speak
```

For local application integration, run `openra-ai-companion serve`. Its small
HTTP API supports snapshot observation, player questions, transcription,
speech, mute/disable controls, and immediate interruption. All model traffic
uses the named BeTenshi routes in the project `.env`; provider keys stay in
BeTenshi and are never copied into this repository.
