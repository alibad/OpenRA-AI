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
  -> advice / "what should we do"?             -> advisor (advisor.py): next step from the
                                                  game state, no model call; open advice
                                                  gets one short call (never the planner)
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

### Offers, prerequisites and advice (7 October live test fixes)

The first live test on real local models (RTSAI-WebGame `tools/cocommander-live.mjs`) found
four problems; this is how each now works.

- **Offers persist.** The companion holds up to three offers (cards). A question, or an order
  for something else, leaves them standing; a newer offer replaces an older one only when it is
  about the same item or the same units (`proposal_subjects` in `core.py`), or when the player
  cancels it ("cancel" cancels the newest, "cancel all" every offer). A bare "confirm" accepts
  the newest. Offers the battlefield makes impossible (a building placed by hand, a unit lost)
  are dropped on the next snapshot. A finished structure always keeps a placement offer, held
  silently behind the player's own cards when it finishes during a question. `/v1/state` keeps
  `pending_action` (the newest offer) and adds `pending_actions` (all of them, newest first).
- **Every faction item is known.** `scripts/build-companion-tech-tree.py` resolves the RTS AI
  mod's rules (MiniYAML inheritance and removals, Fluent names) into
  `services/companion/src/openra_ai_companion/data/tech_tree.json`: for every faction of the
  main mod and of the standalone game, each unit and building with its name, queue, cost and the
  buildings that unlock it, plus the catalogue names from `catalog/factions.json`.
  `techtree.py` picks the profile and faction from the snapshot. An item that is not buildable
  yet is explained and its first step is offered: "Build a barracks" before the Power Plant is
  placed gives *The Barracks needs a Power Plant first* and a card to build (or place) it; a
  prerequisite that is still building is reported with its progress; another faction's unit is
  named as such. Regenerate the data after roster changes:
  `python scripts/build-companion-tech-tree.py --profile rtsai=../RTSAI-Mod@main --profile standalone=../RTSAI-Mod@rtsai/standalone`.
- **Advice is fast.** "What should I build first?" and "what should I do next?" used to run the
  interactive MCP planner (several model calls, 9 to 24 s on the local 2B model). A plain
  next-step question is now decided from the game state (`advisor.py`: place finished
  buildings, fix power, the opening build order, harvesters, army, scouting, attack) with the
  order as a card and no model call; status questions use the deterministic briefing; other
  advice ("should we attack now?") gets one short model call (120 tokens) over a compact state
  summary. The planner remains for AUTO, scouting requests and planner follow-ups.
- **Parsing.** Compass directions ("send the tanks east") ground deterministically (only
  screen-relative words and "that tank" go to the model), "the selected tanks" means all of them
  (the observation has no selection), generic "soldiers" and "tanks" pick the faction's own line
  infantry and battle tank, and the misses of the offline benchmark are parsed (units-first
  attacks and special actions, "put four riflemen in the APC", "turn the radar dome off", "start
  repairs on the factory", "gis deploy", exact words beating sound-alikes). Orders keep the same
  command format, so replays are unaffected.

Offline deterministic benchmark (`run_eval.py --offline`, 281 cases): overall 91.8 % -> 97.2 %,
executable 92.7 % -> 99.5 %, unsafe accepts 0 -> 0. The remaining offline failures are vague
orders that need the model to ask back ("move them", "go over there").

## Evaluation

TBD

## Live end-to-end proof

TBD

## Limitations

TBD
