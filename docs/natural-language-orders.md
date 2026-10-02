# Natural-language orders

Spoken and typed orders ("train three light tanks", "load the infantry into the
APC", "build a power plant") must become dependable for a public release. This
document describes how orders are interpreted, the reproducible evaluation, the
measured results with the shipping local model, the live end-to-end proof, and
what remains limited.

## Pipeline

```text
player text / Whisper transcript
  -> refusal screen (surrender, lifecycle, support powers, cheats, own forces,
     selling everything)                       -> clear refusal, no model call
  -> question?                                 -> one answer call (sanitized)
  -> advice / "what should we do"?             -> existing MCP planner path
  -> deterministic parser (explicit phrasing)  -> typed steps
     otherwise one JSON-schema constrained model call -> typed steps
  -> Python grounding against the fog-respecting snapshot
  -> companion validator -> pending proposal (ACCEPT / "confirm")
  -> ExecuteCompanionActions -> OpenRA game-thread validation -> receipt
```

A *typed step* is an allowlisted verb plus free-text references:

```json
{"action": "move", "units": "all Light Tanks", "count": 0, "item": "", "target": "north", "stance": ""}
```

The model never produces actor ids, coordinates or production ids. Grounding in
`services/companion/src/openra_ai_companion/nl_orders.py` resolves references
with the snapshot's own display names (both mods, all factions), curated
aliases and Whisper-style mis-hearings ("bill the power plan", "harvest hers",
"con scripts", "links" for Lynx, "rod" for Raad), then produces commands that
the unchanged companion validator and OpenRA validate again.

Safety properties are unchanged: proposals are single-player, allowlisted,
capped at twelve orders, require a separate confirmation, and exclude
surrender, hidden state, support powers and match lifecycle. The typed schema
has no support-power verb, and player proposals reject `use_support_power` in
validation. Attacks target only currently visible enemies; last-known enemy
structures are used only as attack-move destinations.

### Why this design

- **Deterministic fast path.** Most real orders are explicit. Parsing them
  directly is instant, cannot be malformed, and does not depend on CPU load.
- **Grammar-constrained decoding.** The shipping runtime is llama.cpp b10430;
  its `response_format: json_schema` support compiles the schema into a GBNF
  grammar, so the 2B local model cannot emit malformed JSON or an action
  outside the enum. External OpenAI-compatible endpoints receive the same field
  and fall back to `json_object`, then prompt-only JSON, if they reject it.
- **One repair attempt.** Output that still fails strict validation (possible
  only for external endpoints without schema support) gets one repair request;
  after that the player sees a short clarification, never model text.
- **Small prompt.** The model sees a compact vocabulary (names and counts only)
  instead of the full per-actor action context, so interpretation fits well
  inside the 20-second router timeout on CPU.

### Multi-step building

`build a power plant` queues production when nothing is queued, reports the
exact progress while it builds (never a duplicate or premature placement), and
proposes `place_building` only once OpenRA reports the structure finished. If no
Construction Yard exists yet, the first legal step (deploying the MCV) is
proposed with a note. The validator now also rejects premature placement from
any path. After a confirmed build, the existing contextual suggestion offers
placement when the structure completes.

## Evaluation

TBD

## Live end-to-end proof

TBD

## Limitations

TBD
