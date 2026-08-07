# Companion service

The companion service turns relevant game context and player speech into short,
interruptible responses.

It owns relevance scoring, cooldowns, deduplication, conversation state,
transcription, speech playback coordination, cancellation, and BeTenshi
routing. OpenAI is the initial inference backend; local models can replace it
without changing the game-facing contract.

The initial companion is observation-only and cannot issue game orders.

