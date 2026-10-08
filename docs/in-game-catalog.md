# In-game faction catalog

The shared catalog (`catalog/factions.json`) now appears in three places: the
public site (RTSAI-Web), the native game, and the AI companion. Every number a
player sees in the game or hears from the companion is read from the engine's
loaded rules for the current mode. The catalog supplies only editorial text:
stories, titles, signature units, roles and counterplay, which mode implements
each faction, and the public page links.

## Native Faction Catalog (engine)

- Open it with **Factions** on the main menu, or with **Open in Faction Catalog**
  on a faction pack in **Factions & Capabilities**. It works in Classic (`ra`)
  and Red Alert 2 (`ra2`).
- It shows only the factions available in the loaded mode. Classic lists China,
  Iran, Türkiye, Saudi Arabia and Yemen, then the original countries. RA2 lists
  China, Iran and Türkiye, then its nine original countries. A note names the
  catalog factions that exist only in another mode, such as "Classic only:
  Saudi Arabia, Yemen". When `ra2-red-sea` flips a faction's RA2 status and its
  RA2 pack exists, it appears in RA2 with no code change.
- Each faction shows its title, tagline, side, doctrine, summary and signature
  units, plus its roster grouped by domain (Infantry, Vehicles, Aircraft, Navy,
  Buildings, Defenses) with the real production icons.
  - Modern factions use their faction pack's roster, plus any unit that only
    that faction can build.
  - Original countries use every actor they can build under the loaded rules;
    units unique to that country are tagged **UNIQUE**.
- Unit details come from the rules: cost, build time, hit points, armor, speed,
  sight, power, transport, attack reach, roles, counters, prerequisites,
  description, and each weapon's range, damage, reload and targets. Signature
  units also show the catalog's field notes.
- **More on the web** and **Unit on the web** open
  `https://rtsai.net/factions/{id}?mode={ra|ra2}` and
  `https://rtsai.net/units/{id}?mode=…`, the RTSAI-Web routes. Link templates
  live in the catalog's additive `links` object and default to these routes.
- Keyboard: Left/Right changes faction, Up/Down changes unit, PageUp/PageDown
  scrolls details, Enter opens the web page, Esc goes back. The panel resizes
  with the window: 1200×680 at 1280×720 and 1440×900 at 1920×1080. Long text
  uses native multiline tooltips and scroll panels.
- Without the catalog file the screen still works from rules alone. Names,
  rosters and statistics remain; web links and editorial text are hidden, and a
  note says the catalog is unavailable.

### Where the game finds the catalog

In order: `OPENRA_AI_CATALOG`, `$OPENRA_AI_ROOT/catalog`, then relative to the
engine directory:

| Layout | Path |
|---|---|
| macOS bundle (engine dir = `Contents/Resources`) | `EngineDir/catalog/factions.json` |
| Windows package, and the product's `engine/openra` submodule | `EngineDir/../../catalog/factions.json` |
| Canonical engine checkout beside this repository | `EngineDir/../OpenRA-AI/catalog/factions.json` |

The packagers already stage the file (`content_catalog.py --stage`), so
installed builds need no extra step. `scripts/prepare-ra2.py` adds the panel's
chrome and messages to the RA2 manifest when the engine ships them.

## Companion access

- The game posts a rules digest to the companion at `POST /v1/factions/live`
  whenever the companion is enabled: from the main menu and the catalog for
  the mod's rules, and from the in-match HUD for that map's rules. The digest
  holds every roster actor for the mode, with statistics, weapons, reach,
  roles and counters.
  - It carries no match state (positions, health or visibility), so catalog
    answers cannot reveal anything hidden by fog of war.
  - `GET /v1/factions?q=…&mode=…` shows the current knowledge.
- `faction_catalog.py` joins the digest to the catalog.
  - Questions that name a faction or unit get a deterministic answer before any
    model is called, for example "what does the Qilin counter?" or "which Yemen
    unit is anti-air?". It is always scoped to the current mode, or to a mode
    the question names.
  - Units and factions from another mode are only named to say they are not
    available in this one; their statistics are never quoted.
  - Orders ("build a Qilin", "can you…"), advice ("should I…") and live-state
    questions ("where is the enemy…") still go to the planner.
- `ask()` adds mode-filtered catalog facts to its prompt. The game-tool MCP
  server has a `faction_catalog` tool for the planner. It reads the same digest
  through the private directory in `OPENRA_AI_FACTION_DIGEST_DIR`.
- Packaged companions find the catalog beside their `bin` directory
  (`<root>/bin/openra-ai-companion.exe` → `<root>/catalog`; macOS
  `Resources/bin` → `Resources/catalog`), or through `OPENRA_AI_ENGINE_DIR`.

## Validation

```powershell
# Structure, links, rules paths (also run by both packagers)
.venv\Scripts\python.exe scripts\content_catalog.py --engine ..\OpenRA
# Per-mode consistency against the engine's merged rules (Classic + data-only RA2)
.venv\Scripts\python.exe scripts\validate-faction-catalog.py --engine ..\OpenRA
# Installed Windows and macOS layouts resolve the staged catalog (add --launch-game for a native screenshot)
.venv\Scripts\python.exe scripts\verify-catalog-package-layout.py --engine ..\OpenRA
```

`validate-faction-catalog.py` runs `OpenRA.Utility <mode> --check-faction-catalog`
with each mode's catalog profile, `world-war-iii` for Classic and `ra2-modern`
for RA2. It fails when:

- a catalog unit's actor is missing from that mode's rules, or its faction
  cannot build it;
- a catalog unit is missing from its faction pack roster;
- a faction pack, or a buildable actor exclusive to one faction, is missing
  from the catalog;
- a unit has a variant for a mode where its faction is unavailable;
- profile membership disagrees;
- a deep link is malformed.

`tests/test_faction_catalog_validation.py` covers these rules with mutated
catalogs. Set `OPENRA_AI_ENGINE_ROOT` when the engine with the catalog is not
the sibling `OpenRA` checkout.

Native captures use `OPENRA_AI_START_FACTION_CATALOG=1` and
`OPENRA_AI_CAPTURE_FACTION_CATALOG=china:cnqilin,@key:RIGHT,@back`, with
`OPENRA_AI_CAPTURE_FACTION_CATALOG_EXIT=1` to exit afterwards. Captures from
Factions & Capabilities add `OPENRA_AI_CAPTURE_FACTION_PACK=<pack>` and
`OPENRA_AI_CAPTURE_OPEN_FACTION_CATALOG=1`.
