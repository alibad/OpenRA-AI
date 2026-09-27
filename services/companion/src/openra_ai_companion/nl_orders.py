"""Natural-language order interpretation for the live companion.

The model is never trusted with actor ids, coordinates or production ids.
Player speech is turned into a small typed intent -- an allowlisted verb plus
free-text references to units, an item and a target -- and deterministic
grounding resolves those references against the latest fog-respecting
snapshot.  Grounded commands still pass the companion's live validator, wait
for a separate player confirmation, and are validated again by the engine.

Two front ends produce the same typed intent:

* a deterministic parser for explicit, common phrasing (no model call); and
* a JSON-schema constrained model call for paraphrase, slang, relative
  directions and anything the parser does not claim.

Both are grounded by :class:`Grounder`, so a model can only change *which*
typed intent is chosen, never invent an executable detail.
"""

from __future__ import annotations

import difflib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .labels import actor_names as classic_actor_names
from .models import GameSnapshot, Unit
from .strategy import desired_harvester_count, maximum_queued_unit_count, maximum_silo_count

MAX_ORDERS = 12

# AUTO's background planner instruction is not player speech.
AUTO_INSTRUCTION_PREFIX = "autonomous commander mode is enabled"

# The verbs the order interpreter may produce.  Support powers, surrender and
# match-lifecycle controls are deliberately absent.
INTENT_ACTIONS = (
    "train", "build", "place", "deploy", "move", "attack_move", "attack", "stop", "harvest",
    "repair", "sell", "rally", "guard", "stance", "load", "unload", "capture", "infiltrate",
    "disguise", "demolish", "primary", "power_down", "cancel",
)

STANCE_NAMES = {0: "hold fire", 1: "return fire", 2: "defend", 3: "attack anything"}

ORDER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"enum": ["command", "question", "clarify", "refuse"]},
        "reply": {"type": "string", "maxLength": 160},
        "steps": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "action": {"enum": list(INTENT_ACTIONS)},
                    "units": {"type": "string", "maxLength": 60},
                    "count": {"type": "integer", "minimum": 0, "maximum": 12},
                    "item": {"type": "string", "maxLength": 60},
                    "target": {"type": "string", "maxLength": 60},
                    "stance": {"enum": ["", "hold fire", "return fire", "defend", "attack anything"]},
                },
                "required": ["action", "units", "count", "item", "target", "stance"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["intent", "reply", "steps"],
    "additionalProperties": False,
}

INTENT_PROMPT = """You convert a real-time strategy player's spoken or typed order into JSON for a game assistant.
Return only the JSON object required by the schema. Never execute anything; later code validates every step.

intent:
- "command": the player wants units, buildings or production to do something.
- "question": the player asks for information or advice and does not give an order.
- "clarify": an order is too vague to act on (missing units, place or item). Put one short question in reply.
- "refuse": surrender, quitting, pausing or restarting the match, cheats, support powers or superweapons
  (nukes, paratroopers, spy plane, iron curtain, chronosphere, airstrikes, weather storm), attacking your own
  forces, selling everything, or revealing hidden enemies. Put one short reason in reply.

For commands, write one step per distinct order (at most 4), in the order the player said them:
- action: train (units) | build (structures) | place (put a finished structure down) | deploy (unpack MCV or deploy a unit)
  | move | attack_move | attack (a visible enemy) | stop | harvest | repair | sell | rally (rally point) | guard (follow and protect one of ours)
  | stance | load (board a transport) | unload | capture | infiltrate | disguise | demolish | primary | power_down | cancel (production).
- units: who carries it out, in the player's words normalized to game names, e.g. "all Light Tanks", "3 Rifle Infantry",
  "idle units", "harvesters", "everyone". Empty for production.
- count: how many to train, or how many units to send; 0 when not stated.
- item: the unit or structure name for train/build/place/cancel/sell/repair/rally/primary/power_down, normalized to the
  closest name in the vocabulary (fix speech-recognition mistakes). Empty otherwise.
- target: where or what, e.g. "enemy base", "our base", "north", "north east", "the War Factory", "visible Rocket Soldier",
  "the Armored Personnel Carrier", "40,52". Empty when there is none.
- stance: only for the stance action.
Use names from the vocabulary. Never output ids. reply is empty for commands and questions.

Examples:
Player: "yo pump out three light tanks" -> {"intent":"command","reply":"","steps":[{"action":"train","units":"","count":3,"item":"Light Tank","target":"","stance":""}]}
Player: "send everybody up north" -> {"intent":"command","reply":"","steps":[{"action":"move","units":"everyone","count":0,"item":"","target":"north","stance":""}]}
Player: "tanks go hit their base" -> {"intent":"command","reply":"","steps":[{"action":"attack_move","units":"all tanks","count":0,"item":"","target":"enemy base","stance":""}]}
Player: "how much money do we have" -> {"intent":"question","reply":"","steps":[]}
Player: "move them" -> {"intent":"clarify","reply":"Which units should move, and where?","steps":[]}
Player: "drop the nuke on them" -> {"intent":"refuse","reply":"Support powers cannot be ordered by voice; use the sidebar.","steps":[]}"""


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

NUMBER_WORDS = {
    "zero": 0, "one": 1, "a single": 1, "single": 1, "two": 2, "a couple of": 2, "a couple": 2, "couple of": 2,
    "couple": 2, "a pair of": 2, "pair of": 2, "three": 3, "a few": 3, "few": 3, "four": 4, "five": 5,
    "six": 6, "half a dozen": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "a dozen": 12, "dozen": 12, "several": 3, "some": 0, "a bunch of": 5, "bunch of": 5,
    "a squad of": 5, "squad of": 5, "a handful of": 3, "handful of": 3,
    "to": None,  # placeholder so "two"/"to" confusions can be looked at below
}
NUMBER_WORDS.pop("to")

# Whisper-style mishearings seen for RTS vocabulary.  Applied to normalized,
# space-separated lowercase text; every entry is a whole-phrase replacement.
ASR_FIXES: tuple[tuple[str, str], ...] = (
    (r"^(bill|built|bilt|guild|bold) ", "build "),
    (r"^(trained|trane|trein|terrain) ", "train "),
    (r"^(depot|deport|the ploy|diploid|the play) (the )?(m c v|mcv|emcee vee|m c b)", "deploy the mcv"),
    (r"\b(emcee vee|em see vee|m c v|m c b|m\.c\.v\.?|mcb)\b", "mcv"),
    (r"\bmobile construction vehicle\b", "mcv"),
    (r"\b(gee eye|g i|g\.i\.?)s?\b", "gi"),
    (r"\bharvest hers\b", "harvesters"),
    (r"\bharvest her\b", "harvester"),
    (r"\b(or|oar|oh|all) (trucks)\b", "ore trucks"),
    (r"\b(or|oar) (truck)\b", "ore truck"),
    (r"\bwar (factor|factories|fact tree|fact ory)\b", "war factory"),
    (r"\b(wharf|wore|war) actory\b", "war factory"),
    (r"\bpower (plan|plans|plane|planet)\b", "power plant"),
    (r"\b(bear|bar) racks\b", "barracks"),
    (r"\bbarrack\b", "barracks"),
    (r"\brifle (men|man)\b", "rifleman"),
    (r"\briffle\b", "rifle"),
    (r"\bengine ears?\b", "engineer"),
    (r"\btesla (coal|call|cool)\b", "tesla coil"),
    (r"\battack moved?\b", "attack move"),
    (r"\battack-move\b", "attack move"),
    (r"\ba[- ]move\b", "attack move"),
    (r"\brally (pointe|pint|paint)\b", "rally point"),
    (r"\bralley\b", "rally"),
    (r"\bcon ?script(s?)\b", r"conscript\1"),
    (r"\bgrenade ?(ears|years|here|hears|ear|ears)\b", "grenadiers"),
    (r"\btech ?nickels?\b", "technicals"),
    (r"\bgimme\b", "give me"),
    (r"^sent ", "send "),
    (r"^(build|make|construct|queue) and (?:then )?(?:place|put down|put) (.+)$", r"\1 \2 and place it"),
    (r"\bgrisly\b", "grizzly"),
    (r"\bryno\b", "rhino"),
    (r"\bmam(m)?oth\b", "mammoth"),
    (r"\bv ?(two|to|2)\b", "v2"),
    (r"\bmedic(k|s)?\b", "medic"),
    (r"\bappc\b", "apc"),
    (r"\ba p c\b", "apc"),
    (r"\bi f v\b", "ifv"),
    (r"\bconst?ruction yard\b", "construction yard"),
    (r"\bcon ?yard\b", "construction yard"),
    (r"\bra(de|d)ar\b", "radar"),
    (r"\brefinary\b", "refinery"),
    (r"\bsilo's\b", "silos"),
    (r"\bhalf track\b", "half-track"),
)

FILLER_PATTERNS = (
    r"^(hey|yo|ok|okay|alright|all right|right|so|um|uh|er|hmm|well|listen|commander|companion|computer|ai)\b[ ,]*",
    r"^(can you|could you|would you|will you|would you kindly|can u|could u|pls|please|kindly)\b[ ,]*",
    r"^(i want you to|i need you to|i would like you to|i'd like you to|i d like you to|go ahead and|go and|let s|lets|let us|we should|we need to|you should|you need to|time to|try to|now)\b[ ,]*",
    r"^(?:can|could) (?:we|i) (?=(?:build|train|make|get|queue|produce|send|move|deploy|place|repair|recruit|buy|have)\b)",
    r"[ ,]*\b(please|pls|thanks|thank you|now|right now|asap|real quick|quickly|immediately|for me|for us|guys|bro|mate|dude|man)\s*$",
)

VERB_WORDS = (
    "build", "construct", "make", "queue", "produce", "train", "recruit", "get", "give", "need", "want", "order",
    "crank", "pump", "spam", "churn", "buy", "place", "put", "drop", "deploy", "unpack", "set", "setup", "move", "go",
    "send", "head", "walk", "drive", "run", "relocate", "reposition", "bring", "take", "retreat", "fall", "pull",
    "withdraw", "regroup", "return", "come", "attack", "kill", "destroy", "hit", "shoot", "engage", "fire", "focus",
    "wipe", "hunt", "assault", "strike", "smash", "crush", "push", "advance", "charge", "sweep", "raid", "storm", "stop",
    "halt", "hold", "cease", "freeze", "harvest", "mine", "gather", "collect", "repair", "fix", "mend", "sell", "scrap",
    "salvage", "rally", "guard", "protect", "escort", "defend", "cover", "load", "board", "enter", "mount", "embark",
    "unload", "dismount", "disembark", "capture", "seize", "infiltrate", "disguise", "demolish", "blow", "plant",
    "cancel", "abort", "dequeue", "power", "turn", "switch", "shut", "prioritize", "patrol", "scout", "use",
)


def _collapse(text: str) -> str:
    return " ".join(text.split())


def number_value(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_TEENS = {"thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
          "nineteen": 19}
_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}


def _spoken_numbers(value: str) -> str:
    """Turn spoken map coordinates such as "forty two" into digits (small counts stay words)."""
    words = value.split()
    output: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        if word in _TENS:
            number = _TENS[word]
            if index + 1 < len(words) and words[index + 1] in _UNITS:
                number += _UNITS[words[index + 1]]
                index += 1
            output.append(str(number))
        elif word in _TEENS:
            output.append(str(_TEENS[word]))
        else:
            output.append(word)
        index += 1
    return " ".join(output)


def normalize(text: str) -> str:
    """Lowercase, expand contractions, repair common ASR errors and strip filler."""
    value = text.replace("’", "'").replace("‘", "'").lower()
    value = re.sub(r"(\d+)\s*,\s*(\d+)", r"\1,\2", value)
    value = value.replace("n't", " not").replace("'s", "s").replace("'re", " are").replace("'ll", " will")
    value = value.replace("'d", " would").replace("'m", " am").replace("'ve", " have")
    value = re.sub(r"[^a-z0-9,\-\s]", " ", value)
    value = re.sub(r"(?<!\d),|,(?!\d)", " ", value)
    value = _collapse(value)
    value = _spoken_numbers(value)
    for pattern, replacement in ASR_FIXES:
        value = re.sub(pattern, replacement, value)
    changed = True
    while changed:
        changed = False
        for pattern in FILLER_PATTERNS:
            stripped = re.sub(pattern, "", value).strip()
            if stripped != value and stripped:
                value = stripped
                changed = True
    return _collapse(value)


def alias_text(value: str) -> str:
    """Normalize a display name or alias the same way spoken text is normalized."""
    value = value.lower()
    value = re.sub(r"\b([a-z])\.(?=[a-z]\b)", r"\1", value)  # G.I. -> gi
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return _collapse(value)


def _plural_stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("men") and len(word) > 4:
        return word[:-3] + "man"
    if len(word) > 3 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    if len(word) == 3 and word.endswith("s") and (word[1].isdigit() or word in {"gis", "vs"}):
        return word[:-1]  # "v2s", "gis"
    return word


def _phonetic(word: str) -> str:
    """A compact Soundex variant; tolerant of ASR spelling changes."""
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return ""
    codes = {**dict.fromkeys("bfpv", "1"), **dict.fromkeys("cgjkqsxz", "2"), **dict.fromkeys("dt", "3"),
             "l": "4", **dict.fromkeys("mn", "5"), "r": "6"}
    first = word[0]
    result = first
    last = codes.get(first, "")
    for character in word[1:]:
        code = codes.get(character, "")
        if code and code != last:
            result += code
        if character not in "hw":
            last = code
    return (result + "000")[:4]


def _token_match(spoken: str, name: str) -> float:
    if spoken == name:
        return 1.0
    if _plural_stem(spoken) == _plural_stem(name):
        return 0.98
    ratio = difflib.SequenceMatcher(None, spoken, name).ratio()
    if (
        len(spoken) >= 3 and len(name) >= 3 and abs(len(spoken) - len(name)) <= 2
        and not spoken.isdigit() and _phonetic(spoken) == _phonetic(name)
    ):
        # "links" -> "lynx", "rod" -> "raad", "tessla" -> "tesla".
        ratio = max(ratio, 0.86)
    return ratio


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

BUILDING_WORDS = {
    "plant", "barracks", "refinery", "factory", "yard", "dome", "radar", "depot", "silo", "wall", "fence",
    "pillbox", "turret", "tower", "coil", "site", "center", "centre", "pad", "airfield", "helipad", "pen", "kennel",
    "generator", "curtain", "chronosphere", "reactor", "command", "lab", "bunker", "cannon", "battery", "vats",
    "sensor", "hospital", "derrick", "outpost", "emplacement", "uplink", "device", "purifier", "gun", "hq",
    "headquarters", "wall", "gate", "barrier", "sandbag", "sandbags", "hand", "dock", "port", "base", "system",
    "autocannon", "fortress", "citadel",
}
UNIT_WORDS = {
    "tank", "infantry", "soldier", "truck", "vehicle", "carrier", "ranger", "engineer", "medic", "spy", "dog",
    "rifleman", "team", "section", "guard", "hunter", "technical", "flak", "launcher", "miner", "harvester", "jet",
    "plane", "helicopter", "boat", "ship", "submarine", "destroyer", "cruiser", "frigate", "drone", "trooper", "gi",
    "conscript", "commando", "sniper", "mechanic", "thief", "apc", "ifv", "mcv", "artillery", "jeep", "buggy",
    "bike", "chopper", "fighter", "bomber", "corvette", "gunboat", "transport", "mirage", "prism", "chrono", "legionnaire",
    "seal", "tanya", "boris", "yuri", "desolator", "terrorist", "crazy", "ivan", "rocketeer", "robot", "squid",
    "dolphin", "hovercraft", "minelayer", "mech", "walker", "howitzer", "rifle", "grenadier",
}

# Generic class words that select several unit types at once.
CLASS_WORDS: dict[str, str] = {
    "army": "combat", "forces": "combat", "force": "combat", "units": "combat", "unit": "combat",
    "everyone": "combat", "everybody": "combat", "everything": "combat", "all": "combat", "troops": "combat",
    "guys": "combat", "boys": "combat", "squad": "combat", "military": "combat", "fighters": "combat",
    "infantry": "infantry", "soldiers": "infantry", "soldier": "infantry", "men": "infantry", "grunts": "infantry",
    "boots": "infantry", "footmen": "infantry", "foot": "infantry", "infantrymen": "infantry",
    "vehicles": "vehicle", "vehicle": "vehicle", "armor": "vehicle", "armour": "vehicle",
    "tanks": "tank", "tank": "tank",
    "aircraft": "air", "planes": "air", "helicopters": "air", "choppers": "air", "air": "air", "jets": "air",
    "ships": "naval", "navy": "naval", "boats": "naval", "fleet": "naval", "naval": "naval", "submarines": "naval",
    "harvesters": "harvester", "harvester": "harvester", "harvs": "harvester", "harv": "harvester", "miners": "harvester",
    "miner": "harvester", "collectors": "harvester", "trucks": "harvester",
}

# Words that pad official names but are rarely spoken ("Qilin Battle Tank").
GENERIC_NAME_WORDS = frozenset({
    "battle", "main", "unit", "team", "section", "system", "mobile", "unmanned", "ground", "defense", "defence",
    "combined", "arm", "armed", "command", "headquarters", "multi", "role", "purpose", "the", "of",
})

# Curated aliases by internal id (Classic RA, RA2 and common modern ids).
ALIASES: dict[str, tuple[str, ...]] = {
    "e1": ("rifle infantry", "rifleman", "rifle", "riflemen", "gi", "gis", "grunt"),
    "e2": ("grenadier", "conscript", "nade"),
    "e3": ("rocket soldier", "rocket infantry", "rocket", "bazooka", "rocket guy", "rpg"),
    "e4": ("flame infantry", "flamethrower", "flamer"),
    "e6": ("engineer", "engie", "engy"),
    "e7": ("tanya",),
    "spy": ("spy",),
    "medi": ("medic",),
    "mech": ("mechanic",),
    "dog": ("attack dog", "dog", "dogs"),
    "harv": ("ore truck", "harvester", "miner", "harv", "war miner"),
    "cmin": ("chrono miner", "harvester", "miner", "ore truck"),
    "mcv": ("mcv", "construction vehicle"),
    "amcv": ("mcv", "construction vehicle"),
    "smcv": ("mcv", "construction vehicle"),
    "fact": ("construction yard", "conyard", "con yard", "cy"),
    "gacnst": ("construction yard", "conyard"),
    "nacnst": ("construction yard", "conyard"),
    "powr": ("power plant", "power", "power station", "generator", "powerplant"),
    "gapowr": ("power plant", "power", "power station", "powerplant"),
    "napowr": ("tesla reactor", "reactor", "power plant", "power"),
    "apwr": ("advanced power plant", "advanced power"),
    "tent": ("barracks", "rax", "allied barracks"),
    "barr": ("barracks", "rax", "soviet barracks"),
    "gapile": ("barracks", "rax", "allied barracks"),
    "nahand": ("barracks", "rax", "soviet barracks"),
    "proc": ("ore refinery", "refinery", "ref"),
    "garefn": ("ore refinery", "refinery", "ref"),
    "narefn": ("ore refinery", "refinery", "ref"),
    "weap": ("war factory", "factory", "vehicle factory", "wf"),
    "gaweap": ("war factory", "factory", "vehicle factory"),
    "naweap": ("war factory", "factory", "vehicle factory"),
    "dome": ("radar dome", "radar", "dome"),
    "fix": ("service depot", "repair pad", "repair depot", "depot"),
    "silo": ("silo", "ore silo"),
    "1tnk": ("light tank",),
    "2tnk": ("medium tank",),
    "3tnk": ("heavy tank",),
    "4tnk": ("mammoth tank", "mammoth"),
    "apc": ("apc", "armored personnel carrier", "personnel carrier"),
    "jeep": ("ranger", "jeep"),
    "arty": ("artillery", "arty"),
    "v2rl": ("v2", "v2 rocket", "v2 launcher"),
    "ftrk": ("mobile flak", "flak truck", "flak"),
    "truk": ("supply truck",),
    "tsla": ("tesla coil", "tesla"),
    "gun": ("turret", "gun turret"),
    "pbox": ("pillbox",),
    "hbox": ("camo pillbox",),
    "ftur": ("flame tower",),
    "sam": ("sam site", "sam"),
    "agun": ("aa gun", "anti air gun"),
    "syrd": ("naval yard", "shipyard"),
    "spen": ("sub pen", "submarine pen"),
    "hpad": ("helipad",),
    "afld": ("airfield",),
    "kenn": ("kennel",),
    "atek": ("tech center", "allied tech center"),
    "stek": ("tech center", "soviet tech center"),
    "sbag": ("sandbag wall", "sandbags"),
    "brik": ("concrete wall", "wall"),
    "fenc": ("wire fence", "fence"),
    "mtnk": ("grizzly", "grizzly tank", "grizzly battle tank"),
    "htnk": ("rhino", "rhino tank"),
    "fv": ("ifv", "infantry fighting vehicle"),
    "htk": ("flak track",),
}

SUPPORT_POWER_TERMS = (
    "nuke", "nuclear strike", "nuclear missile", "nuclear bomb", "nuclear launch", "atom bomb", "a bomb", "missile strike", "paratrooper",
    "paratroops", "paradrop", "para drop", "parabomb", "para bomb", "spy plane", "iron curtain", "chronosphere",
    "chrono shift", "chronoshift", "airstrike", "air strike", "air raid", "lightning storm", "weather storm",
    "support power", "superweapon", "super weapon", "gps satellite", "sonar pulse", "force shield",
    "psychic dominator", "genetic mutator", "ion cannon", "black eagle strike", "carpet bomb",
)


@dataclass(frozen=True)
class Entry:
    item: str
    name: str
    aliases: tuple[str, ...]
    category: str  # "unit" or "building"


def base_type(value: str) -> str:
    return str(value).lower().split("@", 1)[0].split(".", 1)[0]


def _name_category(item: str, name: str) -> str:
    words = re.findall(r"[a-z0-9]+", name.lower())
    if base_type(item) in {"fact", "gacnst", "nacnst", "powr", "apwr", "gapowr", "napowr", "tent", "barr", "proc",
                           "weap", "dome", "fix", "silo", "tsla", "gun", "pbox", "hbox", "ftur", "sam", "agun",
                           "syrd", "spen", "hpad", "afld", "kenn", "atek", "stek", "sbag", "brik", "fenc"}:
        return "building"
    if words:
        head = words[-1]
        if head in BUILDING_WORDS:
            return "building"
        if _plural_stem(head) in UNIT_WORDS or head in UNIT_WORDS:
            return "unit"
    if any(word in BUILDING_WORDS for word in words) and not any(_plural_stem(word) in UNIT_WORDS for word in words):
        return "building"
    return "unit"


class Vocabulary:
    """Player-facing names for everything the snapshot exposes."""

    def __init__(self, snapshot: GameSnapshot) -> None:
        self.snapshot = snapshot
        queue_types = {
            base_type(str(item.get("item", ""))): str(item.get("queue_type", "")).lower()
            for item in snapshot.production
        }
        own_building_types = {base_type(building.kind) for building in snapshot.buildings}
        items: dict[str, str] = {}
        for item in snapshot.available_production:
            items[item.lower()] = snapshot.actor_name(item)
        for entry in snapshot.production:
            item = str(entry.get("item", "")).lower()
            if item:
                items.setdefault(item, snapshot.actor_name(item))
        for actor in (*snapshot.units, *snapshot.buildings, *snapshot.visible_enemies,
                      *snapshot.visible_enemy_buildings, *snapshot.remembered_enemy_buildings):
            items.setdefault(actor.kind.lower(), snapshot.actor_name(actor.kind))
        self.names = items
        self.entries: dict[str, Entry] = {}
        for item, name in items.items():
            category = _name_category(item, name)
            if queue_types.get(base_type(item)) in {"building", "defense"} or base_type(item) in own_building_types:
                category = "building"
            elif queue_types.get(base_type(item)) in {"infantry", "vehicle", "aircraft", "ship", "plane", "helicopter"}:
                category = "unit"
            aliases = {alias_text(name), alias_text(re.sub(r"\s*\(.*?\)", "", name))}
            aliases.update(alias_text(alias) for alias in ALIASES.get(base_type(item), ()))
            self.entries[item] = Entry(item, name, tuple(sorted(alias for alias in aliases if alias)), category)
        # Known names that are not currently available (Classic RA catalog).
        self.catalog: dict[str, str] = {}
        if snapshot.mod_id == "ra":
            self.catalog = {key: value for key, value in classic_actor_names().items() if "husk" not in key}

    def display(self, item: str) -> str:
        return self.names.get(item.lower()) or self.snapshot.actor_name(item)

    @staticmethod
    def score(phrase: str, alias: str) -> float:
        spoken = [_plural_stem(word) for word in phrase.split() if word not in {"the", "a", "an", "my", "our", "some", "of"}]
        name = [_plural_stem(word) for word in alias.split()]
        if not spoken or not name:
            return 0.0
        if " ".join(spoken) == " ".join(name):
            return 1.0
        weights = [0.35 if word in GENERIC_NAME_WORDS else 1.0 for word in name]
        best = [max((_token_match(token, word) for token in spoken), default=0.0) for word in name]
        coverage = sum(weight * value for weight, value in zip(weights, best)) / sum(weights)
        # Penalize spoken words that match nothing in the alias.
        unmatched = [token for token in spoken if max((_token_match(token, word) for word in name), default=0) < 0.8]
        extra = sum(1 for token in unmatched if token not in GENERIC_NAME_WORDS)
        score = coverage - 0.15 * extra
        distinctive = any(value >= 0.85 and word not in GENERIC_NAME_WORDS for word, value in zip(name, best))
        if not unmatched and distinctive:
            # Every spoken word is part of the name ("rhino tank" for "Rhino Heavy Tank").
            score = max(score, 0.9)
        return score

    def match_items(self, phrase: str, candidates: Iterable[str], threshold: float = 0.84) -> list[tuple[str, float]]:
        scored: list[tuple[str, float]] = []
        spoken_id = " ".join(_plural_stem(word) for word in phrase.split() if word not in {"the", "a", "an", "my", "our"})
        for item in candidates:
            entry = self.entries.get(item.lower())
            aliases = entry.aliases if entry else (alias_text(self.display(item)),)
            best = max((self.score(phrase, alias) for alias in aliases), default=0.0)
            if spoken_id and spoken_id == base_type(item):
                # Internal ids ("apc", "mcv") only ever match exactly, never phonetically.
                best = 1.0
            if best >= threshold:
                scored.append((item.lower(), best))
        scored.sort(key=lambda pair: -pair[1])
        if not scored:
            return []
        top = scored[0][1]
        return [pair for pair in scored if pair[1] >= top - 0.02]

    def match_catalog(self, phrase: str, threshold: float = 0.9) -> str | None:
        best: tuple[float, str] | None = None
        for item, name in self.catalog.items():
            aliases = (alias_text(name), *ALIASES.get(base_type(item), ()))
            score = max(self.score(phrase, alias) for alias in aliases)
            if score >= threshold and (best is None or score > best[0]):
                best = (score, name)
        return best[1] if best else None


# ---------------------------------------------------------------------------
# Actor helpers
# ---------------------------------------------------------------------------

def is_husk(unit: Unit) -> bool:
    return "husk" in unit.kind.lower()


def is_harvester(snapshot: GameSnapshot, unit: Unit) -> bool:
    name = snapshot.actor_name(unit.kind).lower()
    return base_type(unit.kind) in {"harv", "cmin", "harvester"} or any(
        word in name for word in ("ore truck", "harvester", "miner", "collector")
    ) or unit.current_activity in {"FindAndDeliverResources", "HarvestResource", "DeliverResources"}


def is_mcv(snapshot: GameSnapshot, unit: Unit) -> bool:
    name = snapshot.actor_name(unit.kind).lower()
    return base_type(unit.kind) in {"mcv", "amcv", "smcv"} or "construction vehicle" in name


def is_transport(snapshot: GameSnapshot, unit: Unit) -> bool:
    name = snapshot.actor_name(unit.kind).lower()
    return unit.passenger_count >= 0 or base_type(unit.kind) in {"apc", "tran", "lst", "hind", "fv", "htk"} or any(
        word in name for word in ("personnel carrier", "infantry carrier", "transport", "infantry fighting vehicle", "flak track", "ifv")
    )


def unit_class(snapshot: GameSnapshot, unit: Unit) -> set[str]:
    classes = set()
    targets = {value.lower() for value in unit.target_types}
    if "infantry" in targets:
        classes.add("infantry")
    if "vehicle" in targets:
        classes.add("vehicle")
    if targets & {"air", "aircraft", "helicopter", "plane"}:
        classes.add("air")
    if targets & {"ship", "water", "submarine", "underwater"}:
        classes.add("naval")
    name = snapshot.actor_name(unit.kind).lower()
    if "tank" in name or base_type(unit.kind) in {"1tnk", "2tnk", "3tnk", "4tnk", "mtnk", "htnk", "ttnk", "ctnk"}:
        classes.add("tank")
        classes.add("vehicle")
    if is_harvester(snapshot, unit):
        classes.add("harvester")
    if unit.can_attack and not is_harvester(snapshot, unit) and not is_mcv(snapshot, unit):
        classes.add("combat")
    return classes


def centroid(actors: Iterable[Unit]) -> tuple[int, int] | None:
    points = [(actor.cell_x, actor.cell_y) for actor in actors]
    if not points:
        return None
    return (round(sum(x for x, _ in points) / len(points)), round(sum(y for _, y in points) / len(points)))


def own_base(snapshot: GameSnapshot) -> tuple[int, int] | None:
    yards = [building for building in snapshot.buildings if base_type(building.kind) in {"fact", "gacnst", "nacnst"}
             or "construction yard" in snapshot.actor_name(building.kind).lower()]
    return centroid(yards) or centroid(snapshot.buildings) or centroid(unit for unit in snapshot.units if not is_husk(unit))


def enemy_base(snapshot: GameSnapshot) -> tuple[tuple[int, int] | None, str]:
    visible = centroid(snapshot.visible_enemy_buildings)
    if visible is not None:
        return visible, "visible"
    remembered = centroid(snapshot.remembered_enemy_buildings)
    if remembered is not None:
        return remembered, "remembered"
    return None, "unknown"


def playable_bounds(snapshot: GameSnapshot) -> tuple[int, int, int, int]:
    if snapshot.mod_id == "ra2":
        return 0, 0, max(1, snapshot.map_width), max(1, snapshot.map_height)
    width = snapshot.map_bounds_width or snapshot.map_width
    height = snapshot.map_bounds_height or snapshot.map_height
    return snapshot.map_bounds_x, snapshot.map_bounds_y, max(1, width), max(1, height)


def clamp_cell(snapshot: GameSnapshot, x: int, y: int, margin: int = 2) -> tuple[int, int]:
    left, top, width, height = playable_bounds(snapshot)
    margin = max(0, min(margin, width // 4, height // 4))
    return (
        min(max(x, left + margin), left + width - 1 - margin),
        min(max(y, top + margin), top + height - 1 - margin),
    )


DIRECTIONS: dict[str, tuple[int, int]] = {
    "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
    "northeast": (1, -1), "north east": (1, -1), "northwest": (-1, -1), "north west": (-1, -1),
    "southeast": (1, 1), "south east": (1, 1), "southwest": (-1, 1), "south west": (-1, 1),
    "up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1),
    "upper left": (-1, -1), "top left": (-1, -1), "upper right": (1, -1), "top right": (1, -1),
    "lower left": (-1, 1), "bottom left": (-1, 1), "lower right": (1, 1), "bottom right": (1, 1),
}


def direction_target(snapshot: GameSnapshot, origin: tuple[int, int], vector: tuple[int, int]) -> tuple[int, int]:
    _, _, width, height = playable_bounds(snapshot)
    distance = max(8, round(min(width, height) / 3))
    dx, dy = vector
    scale = 1 / math.sqrt(2) if dx and dy else 1
    return clamp_cell(snapshot, round(origin[0] + dx * distance * scale), round(origin[1] + dy * distance * scale))


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class Step:
    action: str
    units: str = ""
    count: int = 0
    item: str = ""
    target: str = ""
    stance: str = ""
    source: str = ""


@dataclass
class OrderResult:
    kind: str  # proposal | explain | clarify | refuse | question | advice | defer
    message: str = ""
    summary: str = ""
    commands: list[dict[str, Any]] = field(default_factory=list)
    path: str = "deterministic"
    notes: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)

    def as_metadata(self) -> dict[str, Any]:
        return {"kind": self.kind, "path": self.path, "steps": self.steps, "notes": self.notes}


class GroundingError(ValueError):
    """A reference could not be grounded; the message is player-facing."""

    def __init__(self, message: str, kind: str = "clarify") -> None:
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------------------
# Utterance classification
# ---------------------------------------------------------------------------

LIFECYCLE_PATTERN = re.compile(
    r"\b(surrender|give up|resign|forfeit|concede|throw in the towel|quit|leave the (game|match)|exit|end (the )?(game|match)"
    r"|restart|pause|unpause|save (the )?game|load (a |the )?(game|save)|gg|abandon (the )?(game|match)|reset (the )?(game|match))\b"
)
CHEAT_PATTERN = re.compile(
    r"\b(cheat|cheats|god ?mode|infinite|unlimited|free (money|cash|credits)|give (me|us) (\d+ )?(money|cash|credits|funds)"
    r"|give (?:me|us) (?:[a-z0-9]+ ){0,3}(?:money|cash|credits|funds|resources)"
    r"|(reveal|show me|remove|disable|lift) (the )?(whole |entire )?(map|shroud|fog)|map ?hack|instant(ly)? (win|build|kill)"
    r"|win the (game|match) for|hack|spawn (me |us )?(a |some )?\w+ for free|max (money|cash))\b"
)
SELF_HARM_PATTERN = re.compile(
    r"\b(attack|kill|destroy|shoot|fire on|hit) (my|our) (own )?(units|base|buildings|tanks|troops|army|harvesters?|men|guys|stuff)\b"
    r"|\bfriendly fire\b|\bkill (all )?(my|our) (own )?\w+"
)
SELL_ALL_PATTERN = re.compile(r"\bsell\b.*\b(everything|all|every|entire|whole|each)\b|\bsell (the |my |our )?base\b")
DIPLOMACY_PATTERN = re.compile(r"\b(tell|message|chat with|talk to|ally with|team up with|bribe|negotiate with) (the )?(enemy|opponent|ally|allies|player)\b")
ADVICE_PATTERN = re.compile(
    r"\b(what should (i|we)|should (i|we)|suggest|recommend|advice|advise|next move|what (do|can) (i|we) do|what now|"
    r"help me|any ideas|what would you do|best (move|strategy|counter)|how (do|can|should) (i|we) (win|beat|counter|deal))\b"
)
QUESTION_START = re.compile(
    r"^(what|whats|what is|where|wheres|when|why|how|which|who|whose|is|are|am|was|were|do|does|did|(?:have|has|had) (?:we|i|you|they|our|the enemy|it|he|she|any)|"
    r"can (i|we)|could (i|we)|should|shall|may|might|any|tell me|explain|describe|status|report|how many|how much|"
    r"are we|is there|are there)\b"
)
IMPERATIVE_START = re.compile(r"^(" + "|".join(sorted(VERB_WORDS, key=len, reverse=True)) + r")\b")
REQUEST_QUESTION = re.compile(r"^(can|could|would|will) (you|u)\b")


_STRATEGY_FILLER = frozenset({
    "switch", "change", "use", "adopt", "set", "play", "go", "be", "enable", "to", "the", "a", "an", "our", "my", "more",
    "mode", "style", "posture", "approach", "doctrine", "strategy", "plan", "tactics", "let", "us", "we", "lets", "please",
    "now", "on", "into", "full", "very", "really", "bit", "little", "and", "start", "being", "get", "stay", "keep",
    "adaptive", "adapt", "choose", "balanced", "normal", "standard", "rush", "aggressive", "offensive", "pressure",
    "turtle", "defensive", "defense", "fortify", "fortified", "naval", "navy", "sea", "medium", "measured", "up",
    "strategically", "play style", "playing", "i", "want", "you", "should", "can", "could", "would",
})


def is_strategy_command(text: str) -> bool:
    """True for doctrine switches ("play aggressive"), false for unit orders ("set stance to defensive")."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())
    if re.search(r"\b(strategy|strategies|doctrine|play ?style|posture|game plan)\b", normalized):
        return not re.search(r"\b(stance|rally|build|train|tank|tanks|unit|units|infantry)\b", normalized)
    words = normalized.split()
    return bool(words) and all(word in _STRATEGY_FILLER for word in words)


def support_power_request(normalized: str) -> bool:
    if not any(term in normalized for term in SUPPORT_POWER_TERMS):
        return False
    # Building or selling a superweapon structure is an ordinary production request.
    if re.match(r"^(build|construct|make|queue|place|put|sell|repair|fix|power down|cancel)\b", normalized) and re.search(
        r"\b(silo|device|site|facility|generator|structure|building|reactor|lab|uplink)\b", normalized
    ):
        return False
    return True


def classify(text: str) -> str:
    """Return refuse:<reason> | question | advice | command | unknown."""
    normalized = normalize(text)
    raw = text.strip().lower()
    if not normalized:
        return "unknown"
    if LIFECYCLE_PATTERN.search(normalized) and not re.search(r"\b(exit|quit) (the )?(transport|apc|vehicle)\b", normalized):
        return "refuse:lifecycle"
    if support_power_request(normalized):
        return "refuse:support_power"
    if CHEAT_PATTERN.search(normalized):
        return "refuse:cheat"
    if SELF_HARM_PATTERN.search(normalized):
        return "refuse:self_harm"
    if SELL_ALL_PATTERN.search(normalized):
        return "refuse:sell_all"
    if DIPLOMACY_PATTERN.search(normalized):
        return "refuse:diplomacy"
    requested = bool(REQUEST_QUESTION.match(raw.replace("’", "'")))
    if not requested and ADVICE_PATTERN.search(normalized):
        return "advice"
    if requested:
        return "command"
    if re.match(r"^(can|could) (we|i) (build|train|make|get|send|move|attack|deploy|place|repair)\b", normalized) and not re.search(
        r"\b(yet|afford|still|even|possible|able|allowed)\b", normalized
    ):
        return "command"
    if QUESTION_START.match(normalized) and not IMPERATIVE_START.match(normalized):
        return "question"
    if raw.endswith("?") and not IMPERATIVE_START.match(normalized):
        return "question"
    if IMPERATIVE_START.match(normalized) or re.search(r"\b(" + "|".join(VERB_WORDS) + r")\b", normalized):
        return "command"
    if re.search(r"\b(back to work|get to work|go mining)\b", normalized):
        return "command"
    return "unknown"


REFUSAL_TEXT = {
    "lifecycle": "I can't surrender, quit, pause or restart the match for you; that stays in your hands.",
    "support_power": "Support powers aren't available as voice orders; fire them from the sidebar when they're ready.",
    "cheat": "I can only use what your forces can legitimately see and build; there's no cheat or hidden information.",
    "self_harm": "I won't order attacks on your own forces or base.",
    "sell_all": "I won't sell your whole base; name one specific building if you really want to sell it.",
    "diplomacy": "I can't message or negotiate with other players; I only command your own forces.",
}


# ---------------------------------------------------------------------------
# Deterministic parser
# ---------------------------------------------------------------------------

_TARGET_PREPOSITIONS = r"(?:to|towards|toward|into|onto|at|over to|up to|near|by|next to|around|on|in|inside|in front of|behind)"
_COORD = re.compile(r"\b(?:cell |position |coordinates? |x )?(\d{1,3})(?:,| |, | y | and )(\d{1,3})\b")
# Pronouns and bare demonstratives depend on what the player is looking at;
# "that turret" or "those rocket soldiers" still name a concrete type.
DEICTIC = re.compile(
    r"\b(there|here|it|them|him|her|yourself)\b"
    r"|\b(that|this|those|these)\b(?=\s*$|\s+(?:one|ones|guy|guys|thing|stuff|over|up|down|to|at|in|on|with|and|please)\b)"
)
# Any demonstrative may refer to what is on screen, so the model path attaches
# the fog-respecting views when the profile supports images.
VISUAL_REFERENCE = re.compile(r"\b(that|this|those|these|there|here|it|them|him|her|yourself)\b")


def _strip_count(phrase: str) -> tuple[int, str]:
    phrase = phrase.strip()
    for words, value in sorted(NUMBER_WORDS.items(), key=lambda item: -len(item[0])):
        if re.match(rf"^{re.escape(words)}\b", phrase):
            return value, phrase[len(words):].strip()
    match = re.match(r"^(\d{1,2})\b\s*(x\b)?", phrase)
    if match:
        return int(match.group(1)), phrase[match.end():].strip()
    match = re.match(r"^(a|an|one|another|a new|an extra|one more)\b", phrase)
    if match:
        return 1, phrase[match.end():].strip()
    return 0, phrase


def _split_clauses(normalized: str) -> list[str]:
    parts = re.split(r"\b(?:and then|then|after that|afterwards|also|plus)\b|;|\.", normalized)
    clauses: list[str] = []
    for part in parts:
        part = part.strip(" ,")
        if not part:
            continue
        # "build a barracks and train riflemen": split on "and" only between verbs.
        pieces = re.split(r"\band\b(?=\s+(?:" + "|".join(VERB_WORDS) + r")\b)", part)
        clauses.extend(piece.strip(" ,") for piece in pieces if piece.strip(" ,"))
    return clauses


PRODUCTION_VERBS = r"(?:build|construct|make|queue|queue up|produce|train|recruit|get me|get us|get|give me|give us|we need|i need|i want|need|want|order|crank out|pump out|churn out|spam|buy|add|start|start building|start training|research)"
MOVE_VERBS = r"(?:move|go|send|head|walk|drive|run|relocate|reposition|bring|take|get|march|roll|position|put)"
ATTACK_MOVE_VERBS = r"(?:attack move|push|advance|charge|sweep|raid|storm|rush|assault|invade|go hit|hit|attack|strike|move out and attack)"
ATTACK_VERBS = r"(?:attack|kill|destroy|hit|shoot|engage|fire on|fire at|focus|focus fire|focus fire on|wipe out|take out|hunt|hunt down|smash|crush|strike|target|go after|go for|deal with|eliminate|finish off)"


@dataclass
class ParseContext:
    snapshot: GameSnapshot
    vocabulary: Vocabulary


_VERB_ALTERNATION = "|".join(sorted(VERB_WORDS, key=len, reverse=True))


def _addressed_subject(text: str) -> tuple[str, str]:
    """Split "Tanya, blow up the pump" or "I'd like the infantry to board the APC"."""
    raw = text.strip()
    vocative = re.match(r"^\s*([A-Za-z][A-Za-z0-9 .'\-]{0,40}?)\s*,\s*(.+)$", raw)
    if vocative:
        rest = normalize(vocative.group(2))
        if re.match(rf"^(?:{_VERB_ALTERNATION}|go|get|take|kill|blow|plant)\b", rest):
            subject = normalize(vocative.group(1))
            if subject and not re.fullmatch(r"(ok|okay|alright|hey|yo|so|well|listen|commander|please|now|right|and)", subject):
                return subject, rest
    normalized = normalize(raw)
    wrapped = re.match(
        rf"^(?:i would like|i want|i need|we need|have|get|make|tell|order|i d like)\s+(?:the\s+|my\s+|our\s+|all\s+)?(.+?)\s+to\s+((?:{_VERB_ALTERNATION}|go|get)\b.*)$",
        normalized,
    )
    if wrapped and not re.search(r"\b(to|towards?|into)\s*$", wrapped.group(1)):
        return wrapped.group(1).strip(), wrapped.group(2).strip()
    return "", normalized


def parse_steps(text: str) -> tuple[list[Step], str]:
    """Return typed steps for explicit commands, or ([], reason) when not claimed."""
    subject, normalized = _addressed_subject(text)
    steps: list[Step] = []
    for clause in _split_clauses(normalized):
        step = _parse_clause(clause)
        if step is None:
            return [], f"unparsed clause: {clause}"
        if subject and not step.units and step.action not in {"train", "build", "place", "cancel", "sell", "repair", "rally", "primary", "power_down"}:
            step.units = subject
        steps.append(step)
    return steps[:4], ""


def _parse_clause(clause: str) -> Step | None:
    c = clause.strip()
    c = re.sub(r"^(and|also|then)\s+", "", c)

    # Stance changes.
    stance_map = (
        (r"\b(hold fire|cease fire|do not shoot|dont shoot|weapons hold|stop shooting|stop firing|hold your fire)\b", "hold fire"),
        (r"\b(return fire|only shoot back|fire back)\b", "return fire"),
        (r"\b(defensive stance|defend stance|stance defend|stance to defend|stance defensive|defensive mode|defend mode)\b", "defend"),
        (r"\b(aggressive stance|attack anything|fire at will|weapons free|aggressive mode|stance aggressive|stance to aggressive|attack anything that moves|shoot anything)\b", "attack anything"),
    )
    if re.search(r"\bstance\b", c) or any(re.search(pattern, c) for pattern, _ in stance_map):
        for pattern, stance in stance_map:
            if re.search(pattern, c):
                units = re.sub(pattern, " ", c)
                units = re.sub(r"\b(set|put|switch|change|make|to|stance|on|mode|the|their|your|units?|in|into|only|just|and|go|be)\b", " ", units)
                units = _collapse(units)
                return Step("stance", units=units or "all", stance=stance, source="parser")
        return None

    # Rally points.
    if re.search(r"\b(rally|rally point|waypoint|gathering point|muster point)\b", c):
        match = re.search(rf"\b{_TARGET_PREPOSITIONS}\b\s+(.+)$", re.sub(r"\b(set|the|a|rally|point|points|waypoint|for|of|put|move|place)\b", lambda m: m.group(0), c))
        target = ""
        building = ""
        owner_first = re.search(rf"^(?:set|move|put|place|change)?\s*(?:the\s+|my\s+|our\s+)?(.+?)\s+rally(?: point)?s?\s+\b{_TARGET_PREPOSITIONS}\b\s+(.+)$", c)
        owner_after = re.search(rf"\brally(?: point)?s?\b(?:\s+(?:for|of|on)\s+(?:the\s+|my\s+|our\s+|all\s+)?(.+?))?\s+\b{_TARGET_PREPOSITIONS}\b\s+(.+)$", c)
        if owner_first and owner_first.group(1).strip() not in {"set", "the", "a", ""}:
            building = owner_first.group(1).strip()
            target = owner_first.group(2).strip()
        elif owner_after:
            building = (owner_after.group(1) or "").strip()
            target = owner_after.group(2).strip()
        elif match:
            target = match.group(1).strip()
        return Step("rally", item=building, target=target, source="parser")

    # Cancel production (explicit production wording only; bare "cancel" is proposal cancellation).
    found = re.match(r"^(?:cancel|abort|dequeue|remove|stop building|stop training|stop producing|stop making|stop the production of|stop production of)\s+(?:the\s+|my\s+|that\s+)?(.+?)(?:\s+(?:production|from the queue|in the queue|build|order))?$", c)
    if found and not re.search(r"\b(proposal|order|orders|that|it|this)\b$", c):
        return Step("cancel", item=found.group(1).strip(), source="parser")

    # Power down / up.
    found = re.match(r"^(?:power down|turn off|switch off|shut down|shut off|disable|power off|power up|turn on|switch on|enable|reactivate)\s+(?:the\s+|my\s+|our\s+)?(.+)$", c)
    if found:
        return Step("power_down", item=found.group(1).strip(), source="parser")

    # Primary producer.
    found = re.match(r"^(?:set|make|mark)\s+(?:the\s+|my\s+|our\s+|this\s+)?(.+?)\s+(?:as\s+)?(?:the\s+)?primary(?:\s+\w+)?$", c)
    if found:
        return Step("primary", item=found.group(1).strip(), source="parser")

    # Selling.
    found = re.match(r"^(?:sell|scrap|salvage|liquidate|cash in)\s+(?:off\s+)?(?:the\s+|my\s+|our\s+|that\s+|one\s+|a\s+)?(.+)$", c)
    if found:
        return Step("sell", item=found.group(1).strip(), source="parser")

    # Repair.
    found = re.match(r"^(?:repair|fix|mend|patch up|patch)\s+(?:up\s+)?(.+)$", c)
    if found:
        return Step("repair", item=found.group(1).strip(), source="parser")

    # Deploy (MCV / deployable infantry).
    found = re.match(r"^(?:deploy|unpack|set up|setup|unfold|establish)\s+(?:the\s+|my\s+|our\s+|a\s+)?(.+)$", c)
    if found and not re.search(r"\b(troops|passengers|infantry) from\b", c):
        subject = found.group(1).strip()
        if re.fullmatch(r"(base|a base|the base|our base|camp|mcv|mcvs|construction yard|construction vehicle)", subject):
            subject = "mcv"
        return Step("deploy", units=subject, source="parser")
    if re.fullmatch(r"(?:build|make|set up|start) (?:a |the |our )?base(?: here)?", c):
        return Step("deploy", units="mcv", source="parser")

    # Placement of finished structures.
    found = re.match(r"^(?:place|put down|put|drop|plop|set down|position)\s+(?:the\s+|my\s+|our\s+|a\s+|that\s+)?(.+?)(?:\s+(?:down|somewhere|anywhere))?(?:\s+" + _TARGET_PREPOSITIONS + r"\s+(.+))?$", c)
    if found and not re.search(r"\b(units?|tanks?|infantry|troops|army|harvesters?)\b", found.group(1)):
        return Step("place", item=found.group(1).strip(), target=(found.group(2) or "").strip(), source="parser")

    # Transport loading / unloading.
    found = re.match(r"^(?:unload|dismount|disembark|drop off|empty|unpack the troops from|let out)\s+(?:the\s+|my\s+|our\s+|all\s+)?(.+?)(?:\s+(?:here|now))?$", c)
    if found:
        return Step("unload", units=found.group(1).strip(), source="parser")
    found = re.match(r"^(load|board|mount|embark|put|get|move|send)\s+(?:the\s+|my\s+|our\s+)?(.+?)\s+(?:into|in|onto|on|aboard)\s+(?:the\s+|my\s+|our\s+|a\s+)?(.+)$", c)
    if found and (found.group(1) in {"load", "board", "mount", "embark"} or re.search(
        r"\b(apc|transport|carrier|ifv|personnel|chopper|helicopter|boat|lst|flak track)\b", found.group(3)
    )):
        return Step("load", units=found.group(2).strip(), target=found.group(3).strip(), source="parser")
    found = re.match(r"^(?:load up|load)\s+(?:the\s+|my\s+|our\s+)?(.+)$", c)
    if found and re.search(r"\b(apc|transport|carrier|ifv|personnel)\b", found.group(1)):
        return Step("load", units="infantry", target=found.group(1).strip(), source="parser")
    found = re.match(r"^(?:get in|get into|get inside|climb into|climb in|hop in|hop into|jump in|jump into|board|embark on|embark|mount up in|mount)\s+(?:the\s+|my\s+|our\s+|a\s+)?(.+)$", c)
    if found:
        return Step("load", units="", target=found.group(1).strip(), source="parser")
    found = re.match(r"^(?:send|move|get|sneak|slip)\s+(?:the\s+|my\s+|our\s+)?(spy|spies)\s+(?:into|inside|in)\s+(?:the\s+|their\s+|enemy\s+|that\s+)*(.+)$", c)
    if found:
        return Step("infiltrate", units=found.group(1), target=found.group(2).strip(), source="parser")

    # Special abilities.
    for verb, action in (
        (r"capture|take over|seize|steal", "capture"),
        (r"infiltrate|sneak into", "infiltrate"),
        (r"disguise", "disguise"),
        (r"demolish|blow up|plant c4 on|c4|plant explosives on|plant charges on|place c4 on|bomb", "demolish"),
    ):
        found = re.match(rf"^(?:(?:have|get|send|use|order)\s+(?:the\s+|my\s+|our\s+|an?\s+)?(.+?)\s+(?:to\s+)?)?(?:{verb})\s+(?:the\s+|that\s+|their\s+|an?\s+|enemy\s+)*(.+?)(?:\s+(?:with|using)\s+(?:the\s+|my\s+|our\s+|an?\s+)?(.+))?$", c)
        if found:
            if action == "disguise":
                target = re.sub(r"^(?:(?:as|like)\s+(?:an?\s+|the\s+|one of the\s+|enemy\s+)*)", "", found.group(2).strip())
                target = re.sub(r"^(?:the\s+)?spy\s+(?:as\s+)?(?:an?\s+|the\s+|enemy\s+)*", "", target)
                return Step(action, units=(found.group(1) or found.group(3) or "spy").strip(), target=target, source="parser")
            return Step(action, units=(found.group(1) or found.group(3) or "").strip(), target=found.group(2).strip(), source="parser")

    # Harvesting.
    if re.search(r"\b(harvest|harvesting|mine|mining|gather|collect ore|collecting|back to work|get to work|go mining|resume mining)\b", c) and not re.search(r"\b(build|train|make|queue|produce)\b", c):
        subject = re.sub(r"\b(send|get|make|order|tell|have|the|my|our|back|to|work|harvest|harvesting|mine|mining|gather|collect|ore|go|resume|start|idle|and|gems|field|fields|some|more)\b", " ", c)
        idle = " idle" if re.search(r"\bidle\b", c) else ""
        return Step("harvest", units=(_collapse(subject) or "harvesters") + idle, source="parser")

    # Stop.
    found = re.match(r"^(?:stop|halt|hold position|hold still|hold|freeze|stand down|cease|stay|stay put|wait)\b\s*(.*)$", c)
    if found:
        rest = found.group(1).strip()
        found_subject = re.match(r"^(?:all\s+)?(?:the\s+|my\s+|our\s+)?(.*?)(?:\s+(?:where they are|right there|there|here|moving|attacking|what they are doing))?$", rest)
        subject = (found_subject.group(1) if found_subject else rest).strip()
        if not subject:
            return None
        return Step("stop", units=subject, source="parser")
    found = re.match(r"^(.+?)\s+(?:stop|halt|hold position|freeze|stand down)$", c)
    if found:
        return Step("stop", units=found.group(1).strip(), source="parser")

    # Guard / escort (own targets).
    found = re.match(r"^(?:have\s+|send\s+|use\s+|order\s+)?(?:the\s+|my\s+|our\s+)?(.+?)\s+(?:to\s+)?(?:guard|protect|escort|cover|shadow|follow and protect|babysit)\s+(?:the\s+|my\s+|our\s+)?(.+)$", c)
    if found and not re.match(r"^(guard|protect|escort|cover)$", found.group(1)):
        return Step("guard", units=found.group(1).strip(), target=found.group(2).strip(), source="parser")
    found = re.match(r"^(?:guard|protect|escort|cover|shadow|babysit)\s+(?:the\s+|my\s+|our\s+)?(.+?)(?:\s+with\s+(?:the\s+|my\s+|our\s+)?(.+))?$", c)
    if found:
        target = found.group(1).strip()
        if re.fullmatch(r"(base|the base|our base|home|hq)", target):
            return Step("attack_move", units=(found.group(2) or "army").strip(), target="our base", source="parser")
        return Step("guard", units=(found.group(2) or "").strip(), target=target, source="parser")
    found = re.match(r"^(?:defend|protect)\s+(?:the\s+|our\s+|my\s+)?(base|home|hq|construction yard)(?:\s+with\s+(?:the\s+|my\s+|our\s+)?(.+))?$", c)
    if found:
        return Step("attack_move", units=(found.group(2) or "army").strip(), target="our base", source="parser")

    # Retreat.
    found = re.match(r"^(?:(?:everyone|everybody|all units|all|units|army|troops|the army|the troops|(?:the\s+|my\s+|our\s+)?(.+?))\s+)?(?:retreat|fall back|pull back|withdraw|regroup|come back|come home|go home|return to base|return home|back to base|get back|run away|evacuate|go back)\b(?:\s+(?:to\s+)?(?:the\s+|our\s+)?(?:base|home|hq))?(?:\s+(?:all|everyone|everybody|units))?$", c)
    if found:
        return Step("move", units=(found.group(1) or "everyone").strip(), target="our base", source="parser")
    found = re.match(r"^(?:retreat|pull back|bring back|call back|recall|withdraw)\s+(?:the\s+|my\s+|our\s+|all\s+)?(.+?)(?:\s+(?:to\s+)?(?:the\s+|our\s+)?(?:base|home))?$", c)
    if found:
        return Step("move", units=found.group(1).strip(), target="our base", source="parser")

    # Production.
    found = re.match(rf"^{PRODUCTION_VERBS}\s+(?:up\s+|out\s+|me\s+|us\s+|some\s+|more\s+)*(.+)$", c)
    if found and not re.match(r"^(get|take|bring|send|move)\s+(?:the\s+|my\s+|our\s+|all\s+)?\S+.*\b(to|towards|into|over)\b", c):
        body = found.group(1).strip()
        body = re.sub(r"\s+(?:at|in|from)\s+(?:the\s+)?(?:barracks|war factory|factory|base)$", "", body)
        place_too = bool(re.search(r"\band (?:then )?place (?:it|them)\b|\band put (?:it|them) down\b", body))
        body = re.sub(r"\s+and (?:then )?(?:place|put) (?:it|them)(?: down)?.*$", "", body)
        count, item = _strip_count(body)
        trailing = re.search(r"\s+(?:x\s*(\d{1,2})|(\d{1,2})\s*x|times\s+(\d{1,2}))$", item)
        if trailing:
            # "rifleman x4", "tanks 3x".
            count = int(next(group for group in trailing.groups() if group))
            item = item[: trailing.start()]
        item = re.sub(r"^(?:more|another|extra|new|additional)\s+", "", item)
        item = re.sub(r"\s+(?:please|now|asap|quickly|too|as well)$", "", item)
        if not item:
            return None
        action = "train" if re.match(r"^(train|recruit)\b", c) else "build"
        step = Step(action, count=count, item=item, source="parser")
        if place_too:
            step.target = "place when ready"
        return step

    # Attack a visible enemy or attack-move to a place.
    found = re.match(rf"^(?:(?:send|have|order|get|use|take|tell)\s+)?(?:(?:all\s+)?(?:the\s+|my\s+|our\s+)?(.+?)\s+(?:to\s+)?)?{ATTACK_MOVE_VERBS}\s+(?:move\s+)?(?:to\s+|toward\s+|towards\s+|into\s+|on\s+|at\s+)?(?:the\s+)?(.+)$", c)
    if found and found.group(2):
        subject = (found.group(1) or "").strip()
        target = found.group(2).strip()
        explicit_attack_move = bool(re.search(r"\battack move\b", c))
        target, trailing = _split_trailing_subject(target)
        subject = subject or trailing
        if not subject:
            # "a-move the light tanks to 35,35": units first, then the destination.
            ordered = re.match(r"^(?:all\s+)?(?:the\s+|my\s+|our\s+)?(.+?)\s+(?:to|towards|toward|into|at|onto)\s+(?:the\s+)?(.+)$", target)
            if ordered and not _is_place_reference(ordered.group(1)) and _is_place_reference(ordered.group(2)):
                subject, target = ordered.group(1).strip(), ordered.group(2).strip()
        action = "attack_move" if explicit_attack_move or _is_place_reference(target) else "attack"
        if re.match(r"^(push|advance|charge|sweep|raid|storm|rush|invade)\b", c) or re.search(rf"\b(push|advance|charge|sweep|raid|storm|rush|invade)\b", c):
            action = "attack_move"
        return Step(action, units=subject, target=target, source="parser")
    found = re.match(rf"^{ATTACK_VERBS}\s+(?:the\s+|that\s+|those\s+|their\s+|enemy\s+)*(.+?)(?:\s+with\s+(?:all\s+)?(?:the\s+|my\s+|our\s+)?(.+))?$", c)
    if found:
        target = found.group(1).strip()
        subject = (found.group(2) or "").strip()
        action = "attack_move" if _is_place_reference(target) else "attack"
        return Step(action, units=subject, target=target, source="parser")

    # Movement.
    found = re.match(rf"^(?:{MOVE_VERBS})\s+(?:all\s+)?(?:the\s+|my\s+|our\s+)?(.+?)\s+{_TARGET_PREPOSITIONS}\s+(?:the\s+|our\s+|my\s+)?(.+)$", c)
    if found:
        return Step("move", units=found.group(1).strip(), target=found.group(2).strip(), source="parser")
    found = re.match(rf"^(?:all\s+)?(?:the\s+|my\s+|our\s+)?(.+?)\s+(?:move|go|head|walk|drive|roll|march|advance)\s+(?:to\s+|toward\s+|towards\s+|over to\s+|into\s+)?(?:the\s+|our\s+|my\s+)?(.+)$", c)
    if found and not re.match(r"^(and|then)\b", found.group(1)):
        return Step("move", units=found.group(1).strip(), target=found.group(2).strip(), source="parser")
    found = re.match(rf"^(?:{MOVE_VERBS})\s+(?:all\s+)?(?:the\s+|my\s+|our\s+)?(.+?)\s+(north|south|east|west|northeast|northwest|southeast|southwest|north east|north west|south east|south west|up|down|left|right)(?:\s+(?:side|edge|of the map))?$", c)
    if found:
        return Step("move", units=found.group(1).strip(), target=found.group(2).strip(), source="parser")
    return None


def _split_trailing_subject(target: str) -> tuple[str, str]:
    found = re.match(r"^(.+?)\s+with\s+(?:all\s+)?(?:the\s+|my\s+|our\s+)?(.+)$", target)
    if found:
        return found.group(1).strip(), found.group(2).strip()
    return target, ""


PLACE_WORDS = re.compile(
    r"\b(base|hq|headquarters|home|north|south|east|west|northeast|northwest|southeast|southwest|up|down|left|right|"
    r"top|bottom|center|centre|middle|front|position|area|location|cell|corner|edge|side|flank|here|there|\d+,\d+|\d+ \d+|ore field|ore|gems|bridge|hill)\b"
)


def _is_place_reference(target: str) -> bool:
    target = target.strip()
    if re.search(r"\benemy\b|\btheir\b|\bthem\b", target) and re.search(r"\bbase|hq|structures|buildings|position|positions|side|lines?\b", target):
        return True
    return bool(PLACE_WORDS.search(target)) and not re.search(r"\b(tank|tanks|infantry|soldier|soldiers|trooper|truck|harvester|refinery|factory|barracks|turret|yard|plant)\b", target)


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------

class Grounder:
    def __init__(self, snapshot: GameSnapshot) -> None:
        self.snapshot = snapshot
        self.vocabulary = Vocabulary(snapshot)
        self.notes: list[str] = []
        self.planned_units: dict[str, int] = {}
        self.planned_harvesters = 0
        self.planned_buildings: set[str] = set()

    # -- names ---------------------------------------------------------------
    def name(self, item: str) -> str:
        return self.vocabulary.display(item)

    def plural(self, item: str, count: int) -> str:
        name = self.name(item)
        if count == 1:
            return name
        if name.lower().endswith(("infantry", "section", "team")):
            return name
        if name.endswith("man"):
            return name[:-3] + "men"
        if name.endswith("s"):
            return name
        return name + "s"

    # -- units -----------------------------------------------------------------
    def mobile_units(self) -> list[Unit]:
        # Husks, mission cameras and prisoners are owned actors but not commandable units.
        return [unit for unit in self.snapshot.units if not is_husk(unit) and unit.speed > 0]

    def select_units(self, phrase: str, *, purpose: str, count: int = 0, near: tuple[int, int] | None = None) -> list[Unit]:
        """Resolve a unit reference to owned units, raising GroundingError when unclear."""
        snapshot = self.snapshot
        units = self.mobile_units()
        text = normalize(phrase) if phrase else ""
        idle_only = bool(re.search(r"\bidle\b|\bunused\b|\bdoing nothing\b|\bsitting\b", text))
        text = re.sub(r"\b(idle|unused|doing nothing|sitting around|sitting|the|my|our|all|every|each|of|your|available|remaining|spare|free|units? of)\b", " ", text)
        text = _collapse(text)
        spoken_count, text = _strip_count(text)
        count = count or spoken_count
        text = _collapse(re.sub(r"\b(unit|units|guys)$", lambda m: m.group(0) if text.strip() == m.group(0) else "", text))
        default_class = {
            "attack": "combat", "attack_move": "combat", "guard": "combat", "stance": "combat",
            "move": "combat", "stop": "combat", "harvest": "harvester", "load": "infantry",
            "unload": "transport", "deploy": "mcv", "capture": "capture", "infiltrate": "infiltrate",
            "disguise": "disguise", "demolish": "demolish",
        }.get(purpose, "combat")
        selected: list[Unit]
        if not text or text in {"them", "they", "those", "these"}:
            if text in {"them", "they", "those", "these"} and purpose not in {"harvest", "deploy", "unload"}:
                raise GroundingError("Which units do you mean?")
            selected = self._class_units(default_class)
            if not selected:
                raise GroundingError(self._missing_class_message(default_class))
        else:
            selected = self._resolve_unit_phrase(text, units, purpose)
        if idle_only:
            idle = [unit for unit in selected if unit.idle]
            if not idle:
                raise GroundingError("None of those units are idle right now.", "explain")
            selected = idle
        if purpose in {"attack", "attack_move", "guard", "stance"}:
            fighters = [unit for unit in selected if unit.can_attack]
            if not fighters:
                names = ", ".join(sorted({self.name(unit.kind) for unit in selected}))
                raise GroundingError(f"{names} can't attack.", "explain")
            selected = fighters
        if count and count < len(selected):
            anchor = near or own_base(snapshot) or (0, 0)
            selected = sorted(
                selected,
                key=lambda unit: (not unit.idle, (unit.cell_x - anchor[0]) ** 2 + (unit.cell_y - anchor[1]) ** 2, unit.actor_id),
            )[:count]
        elif count and count > len(selected):
            self.notes.append(f"only {len(selected)} available")
        if len(selected) > MAX_ORDERS:
            anchor = near or own_base(snapshot) or (0, 0)
            total = len(selected)
            selected = sorted(
                selected,
                key=lambda unit: (not unit.idle, (unit.cell_x - anchor[0]) ** 2 + (unit.cell_y - anchor[1]) ** 2, unit.actor_id),
            )[:MAX_ORDERS]
            self.notes.append(f"the {MAX_ORDERS}-order limit covers {MAX_ORDERS} of {total} units")
        return selected

    def _class_units(self, unit_class_name: str) -> list[Unit]:
        snapshot = self.snapshot
        units = self.mobile_units()
        if unit_class_name == "mcv":
            return [unit for unit in units if is_mcv(snapshot, unit)]
        if unit_class_name == "transport":
            return [unit for unit in units if is_transport(snapshot, unit) and unit.passenger_count > 0]
        if unit_class_name == "capture":
            return [unit for unit in units if unit.can_capture]
        if unit_class_name == "infiltrate":
            return [unit for unit in units if unit.can_infiltrate]
        if unit_class_name == "disguise":
            return [unit for unit in units if unit.can_disguise]
        if unit_class_name == "demolish":
            return [unit for unit in units if unit.can_demolish]
        return [unit for unit in units if unit_class_name in unit_class(snapshot, unit)]

    def _missing_class_message(self, unit_class_name: str) -> str:
        return {
            "combat": "You have no combat units for that order right now.",
            "harvester": "You have no harvesters right now.",
            "mcv": "There is no undeployed Mobile Construction Vehicle to deploy.",
            "transport": "None of your transports is carrying passengers.",
            "capture": "You have no unit that can capture buildings.",
            "infiltrate": "You have no unit that can infiltrate buildings.",
            "disguise": "You have no spy to disguise.",
            "demolish": "You have no unit that can plant demolition charges.",
            "infantry": "You have no infantry for that order.",
        }.get(unit_class_name, "You have no units for that order.")

    def _resolve_unit_phrase(self, text: str, units: list[Unit], purpose: str) -> list[Unit]:
        snapshot = self.snapshot
        words = text.split()
        if words and words[-1] in CLASS_WORDS or text in CLASS_WORDS:
            key = text if text in CLASS_WORDS else words[-1]
            unit_class_name = CLASS_WORDS[key]
            qualifier = " ".join(words[:-1]).strip()
            if qualifier and unit_class_name in {"tank", "combat", "vehicle", "infantry"} and qualifier not in CLASS_WORDS:
                # "light tanks", "rocket infantry": prefer an exact type match first.
                typed = self._match_unit_types(text, units)
                if typed:
                    return typed
            selected = self._class_units(unit_class_name)
            if unit_class_name == "combat" and purpose in {"move", "stop"}:
                selected = [unit for unit in units if not is_harvester(snapshot, unit) and not is_mcv(snapshot, unit)]
            if not selected:
                raise GroundingError(self._missing_class_message(unit_class_name), "explain")
            return selected
        if re.fullmatch(r"(mcv|mcvs|construction vehicle|construction vehicles|base|construction yard)", text):
            selected = self._class_units("mcv")
            if not selected:
                raise GroundingError(self._missing_class_message("mcv"), "explain")
            return selected
        typed = self._match_unit_types(text, units)
        if typed:
            return typed
        known = self.vocabulary.match_items(text, self.vocabulary.names.keys()) or (
            [(self.vocabulary.match_catalog(text), 1.0)] if self.vocabulary.match_catalog(text) else []
        )
        if known:
            name = self.name(known[0][0]) if known[0][0] in self.vocabulary.names else known[0][0]
            raise GroundingError(f"You don't have any {name} units right now.", "explain")
        raise GroundingError(f"I couldn't tell which of your units \"{text}\" means.")

    def _match_unit_types(self, text: str, units: list[Unit]) -> list[Unit]:
        kinds = {unit.kind.lower() for unit in units}
        matches = self.vocabulary.match_items(text, kinds)
        if not matches:
            return []
        chosen = {item for item, _ in matches}
        return [unit for unit in units if unit.kind.lower() in chosen]

    # -- places ------------------------------------------------------------------
    def resolve_place(self, phrase: str, *, origin: tuple[int, int] | None, purpose: str) -> tuple[tuple[int, int], str]:
        snapshot = self.snapshot
        text = normalize(phrase)
        text = re.sub(r"^(?:to|towards|toward|into|at|over to|near|by|the|of|on)\s+", "", text)
        text = re.sub(r"^(?:the|our|my)\s+", "", text)
        coordinates = _COORD.search(text)
        if coordinates:
            x, y = int(coordinates.group(1)), int(coordinates.group(2))
            if not snapshot.contains_cell(x, y):
                raise GroundingError(f"Cell {x},{y} is outside the map.", "explain")
            return (x, y), f"cell {x},{y}"
        if re.search(r"\benemy\b|\btheir\b|\bthem\b|\bhostile\b|\bopponent\b|\bfront\b|\bfront line\b", text) and not re.search(r"\bour\b|\bmy\b", text):
            if re.search(r"\b(unit|units|army|forces|troops|tanks|infantry|soldiers|them)\b", text) and not re.search(r"\bbase|hq|structures|buildings\b", text):
                visible = centroid(snapshot.visible_enemies)
                if visible is not None:
                    return visible, "the visible enemy forces"
            location, source = enemy_base(snapshot)
            if location is None:
                visible = centroid(snapshot.visible_enemies)
                if visible is not None and not re.search(r"\bbase|hq|structures|buildings\b", text):
                    return visible, "the visible enemy forces"
                raise GroundingError(
                    "We haven't located the enemy base yet, so I can't send units to it; I can scout for it if you like.",
                    "explain",
                )
            label = "the enemy base" if source == "visible" else "the last-known enemy base"
            return location, label
        if re.fullmatch(r"(base|home|hq|headquarters|our base|my base|main base|base center|construction yard|conyard)", text) or re.search(r"\b(our|my) base\b", text):
            location = own_base(snapshot)
            if location is None:
                raise GroundingError("You have no base location yet.", "explain")
            return location, "our base"
        for words, vector in sorted(DIRECTIONS.items(), key=lambda item: -len(item[0])):
            if re.fullmatch(rf"(?:the\s+)?{words}(?:\s+(?:side|edge|part|of the map|end|flank))?(?:\s+of the map)?", text):
                start = origin or own_base(snapshot) or (0, 0)
                return direction_target(snapshot, start, vector), words
        if re.fullmatch(r"(center|centre|middle)(?: of the map)?", text):
            left, top, width, height = playable_bounds(snapshot)
            return (left + width // 2, top + height // 2), "the map center"
        # Own buildings or units as landmarks.
        own = [*snapshot.buildings, *[unit for unit in snapshot.units if not is_husk(unit)]]
        matches = self.vocabulary.match_items(text, {actor.kind.lower() for actor in own})
        if matches:
            kinds = {item for item, _ in matches}
            anchors = [actor for actor in own if actor.kind.lower() in kinds]
            anchor = min(anchors, key=lambda actor: ((actor.cell_x - (origin or (0, 0))[0]) ** 2 + (actor.cell_y - (origin or (0, 0))[1]) ** 2))
            return (anchor.cell_x, anchor.cell_y), f"the {self.name(anchor.kind)}"
        enemies = [*snapshot.visible_enemies, *snapshot.visible_enemy_buildings]
        matches = self.vocabulary.match_items(text, {actor.kind.lower() for actor in enemies})
        if matches:
            kinds = {item for item, _ in matches}
            anchors = [actor for actor in enemies if actor.kind.lower() in kinds]
            start = origin or own_base(snapshot) or (0, 0)
            anchor = min(anchors, key=lambda actor: (actor.cell_x - start[0]) ** 2 + (actor.cell_y - start[1]) ** 2)
            return (anchor.cell_x, anchor.cell_y), f"the visible enemy {self.name(anchor.kind)}"
        if re.search(r"\b(ore|gems|gem|ore field|resources)\b", text):
            raise GroundingError("I can't pinpoint an ore field from here; say a direction or a building to move toward.")
        raise GroundingError(f"I couldn't find a place called \"{phrase.strip()}\" on the map.")

    def resolve_enemy_target(self, phrase: str, origin: tuple[int, int] | None) -> Unit | None:
        snapshot = self.snapshot
        text = normalize(phrase)
        text = re.sub(r"\b(the|that|those|this|these|their|enemy|enemies|hostile|visible|nearest|closest|a|an|one|of)\b", " ", text)
        text = _collapse(text)
        enemies = [*snapshot.visible_enemies, *snapshot.visible_enemy_buildings]
        start = origin or own_base(snapshot) or (0, 0)
        if not text or text in {"them", "it", "him", "target", "enemy", "units", "unit", "forces", "army", "troops", "attackers", "guys"}:
            if not snapshot.visible_enemies:
                return None
            return min(snapshot.visible_enemies, key=lambda actor: (actor.cell_x - start[0]) ** 2 + (actor.cell_y - start[1]) ** 2)
        matches = self.vocabulary.match_items(text, {actor.kind.lower() for actor in enemies})
        if not matches:
            words = text.split()
            if words and words[-1] in CLASS_WORDS:
                unit_class_name = CLASS_WORDS[words[-1]]
                candidates = [actor for actor in snapshot.visible_enemies if unit_class_name in unit_class(snapshot, actor) or unit_class_name == "combat"]
                if candidates:
                    return min(candidates, key=lambda actor: (actor.cell_x - start[0]) ** 2 + (actor.cell_y - start[1]) ** 2)
            return None
        kinds = {item for item, _ in matches}
        candidates = [actor for actor in enemies if actor.kind.lower() in kinds]
        return min(candidates, key=lambda actor: (actor.cell_x - start[0]) ** 2 + (actor.cell_y - start[1]) ** 2)

    # -- production --------------------------------------------------------------
    def resolve_item(self, phrase: str, *, want: str | None = None) -> tuple[str | None, str]:
        """Return (available item id, display name) or (None, recognized name)."""
        snapshot = self.snapshot
        text = normalize(phrase)
        text = re.sub(r"^(?:the|a|an|my|our|some|more|new|another|extra)\s+", "", text)
        text = re.sub(r"\s+(?:please|now)$", "", text)
        if not text:
            return None, ""
        available = [item.lower() for item in snapshot.available_production]
        pool = [item for item in available if not item.endswith("f") or item in {"silo"}]
        matches = self.vocabulary.match_items(text, pool)
        if want:
            filtered = [(item, score) for item, score in matches if self.vocabulary.entries.get(item, Entry(item, "", (), "unit")).category == want]
            matches = filtered or matches
        if matches:
            # Several generic matches ("tank"): keep the first in palette order.
            ordered = sorted(matches, key=lambda pair: available.index(pair[0]) if pair[0] in available else 999)
            item = ordered[0][0]
            return item, self.name(item)
        words = text.split()
        generic_only = all(word in {"more", "some", "new", "main", "basic", "battle", "regular", "standard", "few"} for word in words[:-1])
        if words and generic_only and words[-1] in CLASS_WORDS and CLASS_WORDS[words[-1]] in {"tank", "infantry", "harvester"}:
            wanted = CLASS_WORDS[words[-1]]
            for item in pool:
                entry = self.vocabulary.entries.get(item)
                name = self.name(item).lower()
                if entry and entry.category == "unit" and (
                    (wanted == "tank" and "tank" in name)
                    or (wanted == "harvester" and any(word in name for word in ("ore truck", "harvester", "miner")))
                ):
                    return item, self.name(item)
            if wanted == "infantry":
                for item in pool:
                    if base_type(item) in {"e1", "e2", "cnrifle", "trrifle", "irbas", "sang", "ymr"}:
                        return item, self.name(item)
        known = self.vocabulary.match_items(text, self.vocabulary.names.keys())
        if known:
            return None, self.name(known[0][0])
        catalog = self.vocabulary.match_catalog(text)
        if catalog:
            return None, catalog
        return None, ""

    def production_command(self, step: Step) -> tuple[list[dict], str]:
        snapshot = self.snapshot
        item, name = self.resolve_item(step.item)
        if item is None and not snapshot.buildings:
            mcvs = [unit for unit in self.mobile_units() if is_mcv(snapshot, unit)]
            if mcvs:
                # First legal step: nothing can be built until the base exists.
                wanted = name or step.item.strip() or "that"
                self.notes.append(f"the {wanted} can be built once the Construction Yard is up")
                return [{"action": "deploy", "actor_id": mcvs[0].actor_id}], "Deploy the Mobile Construction Vehicle first"
        if item is None:
            if name:
                raise GroundingError(
                    f"{name} isn't in your build options right now; it needs a production building or technology you don't have yet.",
                    "explain",
                )
            raise GroundingError(f"I don't recognize \"{step.item}\" as something you can build.")
        category = self.vocabulary.entries.get(item, Entry(item, name, (), "unit")).category
        queued = [entry for entry in snapshot.production if str(entry.get("item", "")).lower() == item]
        if category == "building" or step.action in {"build", "place"} and category == "building":
            return self._building_step(item, queued, step)
        return self._unit_step(item, queued, step)

    def _building_step(self, item: str, queued: list[dict], step: Step) -> tuple[list[dict], str]:
        name = self.name(item)
        if queued:
            entry = queued[0]
            progress = float(entry.get("progress", 0))
            if progress >= 0.999 or int(entry.get("remaining_ticks", 1)) <= 0:
                return [{"action": "place_building", "item_type": item}], f"Place the finished {name}"
            percent = max(0, min(99, round(progress * 100)))
            raise GroundingError(
                f"The {name} is already {percent}% built; I'll offer to place it when it's ready instead of queuing a duplicate.",
                "explain",
            )
        if item in self.planned_buildings:
            return [], ""
        busy = next((entry for entry in self.snapshot.production
                     if str(entry.get("queue_type", "")).lower() == "building"
                     and (float(entry.get("progress", 0)) >= 0.999 or int(entry.get("remaining_ticks", 1)) <= 0)), None)
        self.planned_buildings.add(item)
        if busy is not None:
            waiting = self.name(str(busy.get("item", "")))
            self.notes.append(f"the finished {waiting} still needs placing first")
        self.notes.append(f"I'll offer to place the {name} when it's finished")
        return [{"action": "build", "item_type": item}], f"Build a {name}"

    def _unit_step(self, item: str, queued: list[dict], step: Step) -> tuple[list[dict], str]:
        # An explicit player order is not trimmed by AUTO's economy heuristics; the
        # twelve-order proposal cap and the separate confirmation still apply.
        count = max(1, min(step.count or 1, MAX_ORDERS))
        if step.count and step.count > MAX_ORDERS:
            self.notes.append(f"queued {MAX_ORDERS}, the most one proposal can hold")
        self.planned_units[item] = self.planned_units.get(item, 0) + count
        return [{"action": "train", "item_type": item} for _ in range(count)], f"Train {count} {self.plural(item, count)}"

    # -- buildings ---------------------------------------------------------------
    def select_buildings(self, phrase: str, *, predicate=None) -> list[Unit]:
        snapshot = self.snapshot
        text = normalize(phrase)
        text = re.sub(r"^(?:the|my|our|a|an|that|this)\s+", "", text)
        buildings = [building for building in snapshot.buildings if predicate is None or predicate(building)]
        if not text or text in {"it", "that", "this", "them", "those"}:
            return buildings
        if re.fullmatch(r"(everything|all|all buildings|buildings|the base|base|everything damaged|damaged buildings|all damaged buildings|damaged|anything damaged|our stuff|stuff)", text):
            return buildings
        matches = self.vocabulary.match_items(text, {building.kind.lower() for building in snapshot.buildings})
        kinds = {item for item, _ in matches}
        return [building for building in buildings if building.kind.lower() in kinds]

    def building_named(self, phrase: str) -> list[Unit]:
        text = normalize(phrase)
        text = re.sub(r"^(?:the|my|our|a|an|that|this)\s+", "", text)
        matches = self.vocabulary.match_items(text, {building.kind.lower() for building in self.snapshot.buildings})
        kinds = {item for item, _ in matches}
        return [building for building in self.snapshot.buildings if building.kind.lower() in kinds]

    # -- step dispatch -----------------------------------------------------------
    def ground(self, step: Step) -> tuple[list[dict], str]:
        action = step.action
        snapshot = self.snapshot
        if action in {"train", "build"}:
            if not step.item.strip():
                raise GroundingError("What should I build or train?")
            return self.production_command(step)
        if action == "place":
            return self._place(step)
        if action == "deploy":
            return self._deploy(step)
        if action in {"move", "attack_move"}:
            return self._move(step)
        if action == "attack":
            return self._attack(step)
        if action == "stop":
            units = self.select_units(step.units or "everyone", purpose="stop", count=step.count)
            return [{"action": "stop", "actor_id": unit.actor_id} for unit in units], f"Stop {self.describe_units(units)}"
        if action == "harvest":
            units = self.select_units(step.units or "harvesters", purpose="harvest", count=step.count)
            harvesters = [unit for unit in units if is_harvester(snapshot, unit)]
            if not harvesters:
                raise GroundingError("Only harvesters can gather ore.", "explain")
            return [{"action": "harvest", "actor_id": unit.actor_id} for unit in harvesters], f"Send {self.describe_units(harvesters)} to harvest"
        if action == "repair":
            return self._repair(step)
        if action == "sell":
            return self._sell(step)
        if action == "rally":
            return self._rally(step)
        if action == "guard":
            return self._guard(step)
        if action == "stance":
            return self._stance(step)
        if action == "load":
            return self._load(step)
        if action == "unload":
            subject = normalize(step.units or "")
            if not subject or re.fullmatch(
                r"(?:the\s+|my\s+|our\s+|all\s+)*(troops|infantry|passengers|men|guys|soldiers|everyone|them|transports?|units)(?:\s+(?:from|out of)\s+.*)?",
                subject,
            ):
                units = self.mobile_units()
            else:
                units = self.select_units(step.units, purpose="unload")
            loaded = [unit for unit in units if is_transport(snapshot, unit) and unit.passenger_count > 0]
            if not loaded:
                raise GroundingError("None of your transports is carrying passengers.", "explain")
            return [{"action": "unload", "actor_id": unit.actor_id} for unit in loaded], f"Unload {self.describe_units(loaded)}"
        if action in {"capture", "infiltrate", "disguise", "demolish"}:
            return self._special(step)
        if action == "primary":
            buildings = self.building_named(step.item or step.target)
            if not buildings:
                raise GroundingError("Which production building should become primary?")
            building = buildings[0]
            return [{"action": "set_primary", "actor_id": building.actor_id}], f"Make the {self.name(building.kind)} primary"
        if action == "power_down":
            buildings = self.building_named(step.item or step.target)
            if not buildings:
                raise GroundingError("Which building should I power down?")
            building = buildings[0]
            kind = base_type(building.kind)
            name = self.name(building.kind)
            toggleable = kind in {"mslo", "gap", "iron", "pdox", "tsla", "agun", "dome", "sam"} or any(
                word in name.lower() for word in (
                    "radar", "tesla coil", "gap generator", "sam site", "aa gun", "anti-air", "missile silo",
                    "iron curtain", "chronosphere", "patriot", "flak cannon", "prism tower", "psychic sensor",
                    "spy satellite", "weather control", "air defense",
                )
            )
            if not toggleable:
                raise GroundingError(f"The {name} can't be powered down.", "explain")
            return [{"action": "power_down", "actor_id": building.actor_id}], f"Toggle power on the {name}"
        if action == "cancel":
            item, name = self.resolve_item(step.item)
            candidates = [str(entry.get("item", "")).lower() for entry in snapshot.production]
            matches = self.vocabulary.match_items(normalize(step.item), candidates)
            if not matches:
                shown = name or step.item
                raise GroundingError(f"Nothing called {shown} is in production.", "explain")
            chosen = matches[0][0]
            return [{"action": "cancel_production", "item_type": chosen}], f"Cancel {self.name(chosen)} production"
        raise GroundingError("I can't turn that into an order.")

    def describe_units(self, units: list[Unit]) -> str:
        counts: dict[str, int] = {}
        for unit in units:
            counts[unit.kind.lower()] = counts.get(unit.kind.lower(), 0) + 1
        parts = [f"{count} {self.plural(kind, count)}" for kind, count in sorted(counts.items(), key=lambda pair: -pair[1])]
        if len(parts) > 3:
            return f"{len(units)} units"
        return ", ".join(parts)

    def _place(self, step: Step) -> tuple[list[dict], str]:
        snapshot = self.snapshot
        text = normalize(step.item)
        complete = [entry for entry in snapshot.production
                    if str(entry.get("queue_type", "")).lower() in {"building", "defense", ""}
                    and (float(entry.get("progress", 0)) >= 0.999 or int(entry.get("remaining_ticks", 1)) <= 0)]
        if not text or text in {"it", "that", "this", "building", "the building", "structure", "them"}:
            if len(complete) == 1:
                item = str(complete[0].get("item", "")).lower()
                return self._placement(item, step)
            if not complete:
                raise GroundingError("No finished building is waiting to be placed.", "explain")
            names = ", ".join(self.name(str(entry.get("item", ""))) for entry in complete)
            raise GroundingError(f"Which one should I place: {names}?")
        item, name = self.resolve_item(text, want="building")
        in_queue = [str(entry.get("item", "")).lower() for entry in snapshot.production]
        matches = self.vocabulary.match_items(text, in_queue)
        if matches:
            item = matches[0][0]
        if item is None:
            if name:
                raise GroundingError(f"{name} isn't available to build or place right now.", "explain")
            raise GroundingError(f"I don't recognize \"{step.item}\" as a building.")
        queued = [entry for entry in snapshot.production if str(entry.get("item", "")).lower() == item]
        if queued:
            entry = queued[0]
            if float(entry.get("progress", 0)) >= 0.999 or int(entry.get("remaining_ticks", 1)) <= 0:
                return self._placement(item, step)
            percent = max(0, min(99, round(float(entry.get("progress", 0)) * 100)))
            raise GroundingError(
                f"The {self.name(item)} is only {percent}% built, so it can't be placed yet; I'll offer placement when it's ready.",
                "explain",
            )
        # Nothing queued: production has to come first.
        commands, summary = self._building_step(item, [], step)
        return commands, summary

    def _placement(self, item: str, step: Step) -> tuple[list[dict], str]:
        command: dict[str, Any] = {"action": "place_building", "item_type": item}
        coordinates = _COORD.search(normalize(step.target or ""))
        if coordinates and self.snapshot.contains_cell(int(coordinates.group(1)), int(coordinates.group(2))):
            command["target_x"] = int(coordinates.group(1))
            command["target_y"] = int(coordinates.group(2))
        return [command], f"Place the {self.name(item)}"

    def _deploy(self, step: Step) -> tuple[list[dict], str]:
        snapshot = self.snapshot
        text = normalize(step.units or "mcv")
        if re.fullmatch(r"(?:the\s+)?(mcv|mcvs|construction vehicle|construction vehicles|base|construction yard|it)", text):
            mcvs = [unit for unit in self.mobile_units() if is_mcv(snapshot, unit)]
            if not mcvs:
                if any(base_type(building.kind) in {"fact", "gacnst", "nacnst"} for building in snapshot.buildings):
                    raise GroundingError("Your Construction Yard is already deployed.", "explain")
                raise GroundingError("There is no Mobile Construction Vehicle to deploy.", "explain")
            return [{"action": "deploy", "actor_id": unit.actor_id} for unit in mcvs[:MAX_ORDERS]], "Deploy the Mobile Construction Vehicle"
        units = self.select_units(step.units, purpose="deploy")
        deployable = [unit for unit in units if is_mcv(snapshot, unit) or (
            snapshot.mod_id == "ra2" and base_type(unit.kind) in {"e1", "ggi", "gi", "sieg", "ttnk", "shad"}
        )]
        if not deployable:
            names = ", ".join(sorted({self.name(unit.kind) for unit in units}))
            raise GroundingError(f"{names} can't deploy.", "explain")
        return [{"action": "deploy", "actor_id": unit.actor_id} for unit in deployable], f"Deploy {self.describe_units(deployable)}"

    def _move(self, step: Step) -> tuple[list[dict], str]:
        snapshot = self.snapshot
        purpose = step.action
        units = self.select_units(step.units or "everyone", purpose=purpose, count=step.count)
        origin = centroid(units)
        if not step.target.strip():
            raise GroundingError("Where should they go?")
        target, label = self.resolve_place(step.target, origin=origin, purpose=purpose)
        verb = "Attack-move" if purpose == "attack_move" else "Move"
        commands = [{"action": purpose, "actor_id": unit.actor_id, "target_x": target[0], "target_y": target[1]} for unit in units]
        return commands, f"{verb} {self.describe_units(units)} to {label}"

    def _attack(self, step: Step) -> tuple[list[dict], str]:
        snapshot = self.snapshot
        text = normalize(step.target)
        if _is_place_reference(text) or re.search(r"\bbase\b", text):
            step.action = "attack_move"
            return self._move(step)
        units = self.select_units(step.units or "army", purpose="attack", count=step.count)
        origin = centroid(units)
        enemy = self.resolve_enemy_target(step.target, origin)
        if enemy is None:
            known = self.vocabulary.match_items(text, self.vocabulary.names.keys()) or (
                [(self.vocabulary.match_catalog(text) or "", 1.0)] if self.vocabulary.match_catalog(text) else []
            )
            if not snapshot.visible_enemies and not snapshot.visible_enemy_buildings:
                raise GroundingError(
                    "No enemies are visible right now, so there's nothing I can target; I can scout or attack-move if you name a place.",
                    "explain",
                )
            name = self.name(known[0][0]) if known and known[0][0] in self.vocabulary.names else (known[0][0] if known else text)
            raise GroundingError(
                f"I can't see an enemy {name}; I only target enemies that are visible right now.",
                "explain",
            )
        commands = [{"action": "attack", "actor_id": unit.actor_id, "target_actor_id": enemy.actor_id} for unit in units]
        return commands, f"Attack the visible {self.name(enemy.kind)} with {self.describe_units(units)}"

    def _repair(self, step: Step) -> tuple[list[dict], str]:
        buildings = self.select_buildings(step.item or step.target or "damaged buildings")
        if not buildings:
            _, known = self.resolve_item(step.item or step.target or "")
            label = known or re.sub(r"^(?:the|my|our)\s+", "", normalize(step.item or step.target or "that building"))
            raise GroundingError(f"You don't have a {label} to repair.", "explain")
        damaged = [building for building in buildings if building.hp_percent < 0.999]
        if not damaged:
            if len(buildings) == 1:
                raise GroundingError(f"The {self.name(buildings[0].kind)} is already at full health.", "explain")
            raise GroundingError("None of those buildings is damaged.", "explain")
        pending = [building for building in damaged if not building.repairing]
        if not pending:
            raise GroundingError("Those buildings are already being repaired.", "explain")
        pending = sorted(pending, key=lambda building: building.hp_percent)[:MAX_ORDERS]
        names = ", ".join(self.name(building.kind) for building in pending[:3])
        return [{"action": "repair", "actor_id": building.actor_id} for building in pending], f"Repair {names}"

    def _sell(self, step: Step) -> tuple[list[dict], str]:
        text = normalize(step.item)
        if re.fullmatch(r"(everything|all|all buildings|base|the base|buildings)", text):
            raise GroundingError(REFUSAL_TEXT["sell_all"], "refuse")
        buildings = self.building_named(text)
        if not buildings:
            if self.select_units(text, purpose="sell") if False else None:
                pass
            raise GroundingError("Only your own buildings can be sold; which building do you mean?", "clarify")
        building = sorted(buildings, key=lambda candidate: candidate.hp_percent)[0]
        if base_type(building.kind) in {"fact", "gacnst", "nacnst"} or "construction yard" in self.name(building.kind).lower():
            raise GroundingError("I won't sell your Construction Yard by voice; do that from the sidebar if you really mean it.", "refuse")
        return [{"action": "sell", "actor_id": building.actor_id}], f"Sell the {self.name(building.kind)}"

    def _rally(self, step: Step) -> tuple[list[dict], str]:
        snapshot = self.snapshot

        def producer(building: Unit) -> bool:
            name = self.name(building.kind).lower()
            return any(word in name for word in ("barracks", "war factory", "naval yard", "sub pen", "helipad", "airfield", "kennel", "shipyard", "air force", "factory")) and "construction" not in name

        text = normalize(step.item)
        if text and text not in {"all", "production", "production buildings", "everything", "them"}:
            buildings = [building for building in self.building_named(text) if producer(building)]
            if not buildings:
                raise GroundingError(f"You don't have a production building called {step.item}.", "explain")
        else:
            buildings = [building for building in snapshot.buildings if producer(building)]
            if not buildings:
                raise GroundingError("You have no Barracks or War Factory to set a rally point on.", "explain")
        if not step.target.strip():
            raise GroundingError("Where should the rally point be?")
        target, label = self.resolve_place(step.target, origin=centroid(buildings), purpose="rally")
        commands = [{"action": "set_rally_point", "actor_id": building.actor_id, "target_x": target[0], "target_y": target[1]} for building in buildings[:MAX_ORDERS]]
        names = ", ".join(sorted({self.name(building.kind) for building in buildings}))
        return commands, f"Set the {names} rally point to {label}"

    def _guard(self, step: Step) -> tuple[list[dict], str]:
        snapshot = self.snapshot
        text = normalize(step.target)
        own = [*snapshot.buildings, *self.mobile_units()]
        matches = self.vocabulary.match_items(re.sub(r"^(?:the|my|our)\s+", "", text), {actor.kind.lower() for actor in own})
        if not matches:
            words = text.split()
            if words and words[-1] in CLASS_WORDS and CLASS_WORDS[words[-1]] == "harvester":
                matches = [(unit.kind.lower(), 1.0) for unit in self.mobile_units() if is_harvester(snapshot, unit)][:1]
        if not matches:
            if re.search(r"\benemy\b|\btheir\b", text):
                raise GroundingError("Guard orders protect your own units or buildings; say attack for enemies.", "clarify")
            raise GroundingError(f"Which of your units or buildings should be guarded?")
        kinds = {item for item, _ in matches}
        target = next(actor for actor in own if actor.kind.lower() in kinds)
        units = [unit for unit in self.select_units(step.units or "army", purpose="guard", count=step.count) if unit.actor_id != target.actor_id]
        if not units:
            raise GroundingError("There are no other combat units to guard it.", "explain")
        commands = [{"action": "guard", "actor_id": unit.actor_id, "target_actor_id": target.actor_id} for unit in units]
        return commands, f"Have {self.describe_units(units)} guard the {self.name(target.kind)}"

    def _stance(self, step: Step) -> tuple[list[dict], str]:
        names = {value: key for key, value in STANCE_NAMES.items()}
        stance = names.get(step.stance.strip().lower())
        if stance is None:
            raise GroundingError("Which stance: hold fire, return fire, defend, or attack anything?")
        units = self.select_units(step.units or "army", purpose="stance", count=step.count)
        return [{"action": "set_stance", "actor_id": unit.actor_id, "target_x": stance} for unit in units], (
            f"Set {self.describe_units(units)} to {STANCE_NAMES[stance]}"
        )

    def _load(self, step: Step) -> tuple[list[dict], str]:
        snapshot = self.snapshot
        transports = [unit for unit in self.mobile_units() if is_transport(snapshot, unit)]
        text = normalize(step.target)
        if text:
            matches = self.vocabulary.match_items(re.sub(r"^(?:the|my|our|a)\s+", "", text), {unit.kind.lower() for unit in transports})
            if matches:
                kinds = {item for item, _ in matches}
                transports = [unit for unit in transports if unit.kind.lower() in kinds]
        if not transports:
            raise GroundingError("You have no transport to load into.", "explain")
        transport = transports[0]
        units = [unit for unit in self.select_units(step.units or "infantry", purpose="load", count=step.count)
                 if unit.actor_id != transport.actor_id and "infantry" in unit_class(snapshot, unit)]
        if not units:
            raise GroundingError("Only infantry can board that transport.", "explain")
        capacity = 5
        free = capacity - max(0, transport.passenger_count)
        if free <= 0:
            raise GroundingError(f"The {self.name(transport.kind)} is already full.", "explain")
        units = units[:free]
        commands = [{"action": "enter_transport", "actor_id": unit.actor_id, "target_actor_id": transport.actor_id} for unit in units]
        return commands, f"Load {self.describe_units(units)} into the {self.name(transport.kind)}"

    def _special(self, step: Step) -> tuple[list[dict], str]:
        snapshot = self.snapshot
        action = step.action
        units = self.select_units(step.units or "", purpose=action)
        field_name = {
            "capture": "valid_capture_targets",
            "infiltrate": "valid_infiltration_targets",
            "disguise": "valid_disguise_targets",
            "demolish": "valid_demolition_targets",
        }[action]
        able = [unit for unit in units if getattr(unit, field_name)]
        if not able:
            raise GroundingError({
                "capture": "No capturable building is visible to your engineers right now.",
                "infiltrate": "No building your spy can infiltrate is visible right now.",
                "disguise": "There's no visible unit your spy can disguise as right now.",
                "demolish": "No valid demolition target is visible right now.",
            }[action], "explain")
        everyone = {actor.actor_id: actor for actor in (*snapshot.visible_enemies, *snapshot.visible_enemy_buildings, *snapshot.units, *snapshot.buildings)}
        unit = able[0]
        targets = [everyone[target] for target in getattr(unit, field_name) if target in everyone]
        text = normalize(step.target)
        text = re.sub(r"\b(the|that|their|enemy|a|an|one|of|visible|nearest|closest|building|buildings|structure)\b", " ", text)
        text = _collapse(text)
        chosen: Unit | None = None
        if text and targets:
            matches = self.vocabulary.match_items(text, {target.kind.lower() for target in targets})
            if matches:
                kinds = {item for item, _ in matches}
                chosen = min((target for target in targets if target.kind.lower() in kinds),
                             key=lambda target: (target.cell_x - unit.cell_x) ** 2 + (target.cell_y - unit.cell_y) ** 2)
            else:
                raise GroundingError(
                    f"That isn't a valid {action} target right now. Valid targets: "
                    + ", ".join(sorted({self.name(target.kind) for target in targets})[:5]) + ".",
                    "clarify",
                )
        elif targets:
            if len({target.kind.lower() for target in targets}) == 1 or action in {"demolish", "capture", "infiltrate"}:
                chosen = min(targets, key=lambda target: (target.cell_x - unit.cell_x) ** 2 + (target.cell_y - unit.cell_y) ** 2)
            else:
                raise GroundingError(
                    "What should the spy disguise as? Options: " + ", ".join(sorted({self.name(target.kind) for target in targets})[:5]) + ".",
                    "clarify",
                )
        if chosen is None:
            raise GroundingError("No valid target is visible for that right now.", "explain")
        verb = {"capture": "Capture", "infiltrate": "Infiltrate", "disguise": "Disguise as", "demolish": "Demolish"}[action]
        return [{"action": action, "actor_id": unit.actor_id, "target_actor_id": chosen.actor_id}], (
            f"{verb} the {self.name(chosen.kind)} with the {self.name(unit.kind)}"
        )


def ground_steps(snapshot: GameSnapshot, steps: list[Step], *, path: str) -> OrderResult:
    """Ground typed steps; produce one proposal or a single clear explanation."""
    grounder = Grounder(snapshot)
    commands: list[dict] = []
    summaries: list[str] = []
    problems: list[GroundingError] = []
    for step in steps:
        try:
            step_commands, summary = grounder.ground(step)
        except GroundingError as error:
            problems.append(error)
            continue
        # "deploy the MCV and build a power plant" can ground to the same order twice.
        step_commands = [command for command in step_commands if "actor_id" not in command or command not in commands]
        if not step_commands:
            continue
        if len(commands) + len(step_commands) > MAX_ORDERS:
            step_commands = step_commands[: MAX_ORDERS - len(commands)]
            grounder.notes.append(f"trimmed to the {MAX_ORDERS}-order limit")
        commands.extend(step_commands)
        if summary:
            summaries.append(summary)
        if len(commands) >= MAX_ORDERS:
            break
    described = [
        {"action": step.action, "units": step.units, "count": step.count, "item": step.item, "target": step.target,
         "stance": step.stance}
        for step in steps
    ]
    if commands:
        extra = [str(problem) for problem in problems]
        message_parts = []
        if extra:
            message_parts.append(" ".join(extra))
        if grounder.notes:
            message_parts.append("Note: " + "; ".join(dict.fromkeys(grounder.notes)) + ".")
        return OrderResult(
            "proposal",
            " ".join(message_parts),
            summary="; ".join(summaries)[:170],
            commands=commands,
            path=path,
            notes=list(dict.fromkeys(grounder.notes)),
            steps=described,
        )
    if problems:
        first = problems[0]
        return OrderResult(first.kind, str(first), path=path, steps=described)
    return OrderResult("clarify", "Could you say which units should do what?", path=path, steps=described)


def _bare_production(normalized: str, snapshot: GameSnapshot) -> OrderResult | None:
    """A bare production name ("power plant please", "or truck", "grizzly x2") is an order."""
    count, phrase = _strip_count(normalized)
    trailing = re.search(r"\s+(?:x\s*(\d{1,2})|(\d{1,2})\s*x)$", phrase)
    if trailing:
        count = int(next(group for group in trailing.groups() if group))
        phrase = phrase[: trailing.start()]
    if not phrase:
        return None
    vocabulary = Vocabulary(snapshot)
    matches = vocabulary.match_items(phrase, [item.lower() for item in snapshot.available_production], threshold=0.9)
    if not matches:
        return None
    return ground_steps(snapshot, [Step("build", count=count, item=phrase, source="parser")], path="deterministic")


def interpret_deterministic(text: str, snapshot: GameSnapshot) -> OrderResult | None:
    """Fast path: claim explicit commands whose every reference is concrete."""
    category = classify(text)
    if category.startswith("refuse:"):
        return OrderResult("refuse", REFUSAL_TEXT[category.split(":", 1)[1]], path="deterministic")
    normalized = normalize(text)
    if category == "unknown":
        return _bare_production(normalized, snapshot)
    if category != "command":
        return None
    # Deictic and relative references benefit from the model (and vision).
    if DEICTIC.search(normalized) and not re.search(r"\b(place|put) (it|that|them)\b|^(place|put) (it|that)", normalized):
        return None
    steps, _ = parse_steps(text)
    if not steps:
        return _bare_production(normalized, snapshot)
    for step in steps:
        target = normalize(step.target)
        if step.action in {"move", "attack_move", "rally"} and target:
            bare_direction = any(re.fullmatch(rf"(?:the\s+)?{words}(?:\s+\w+)?", target) for words in DIRECTIONS)
            if bare_direction and not re.search(r"\b(base|map)\b", target):
                return None
        if step.action in {"move", "attack_move"} and not target:
            return None
    result = ground_steps(snapshot, steps, path="deterministic")
    if result.kind == "clarify" and any(step.source == "parser" for step in steps):
        # The parser was not confident enough; let the model interpret it.
        return None
    return result


# ---------------------------------------------------------------------------
# Model path
# ---------------------------------------------------------------------------

def vocabulary_context(snapshot: GameSnapshot) -> str:
    """Compact, fog-respecting vocabulary for the intent model (no ids)."""
    def counted(actors: Iterable[Unit], *, idle: bool = False) -> str:
        counts: dict[str, list[int]] = {}
        for actor in actors:
            if is_husk(actor):
                continue
            key = snapshot.actor_name(actor.kind)
            entry = counts.setdefault(key, [0, 0])
            entry[0] += 1
            entry[1] += int(actor.idle)
        parts = []
        for name, (total, idle_count) in sorted(counts.items()):
            label = f"{name} x{total}" if total > 1 else name
            if idle and idle_count and total > 1:
                label += f" ({idle_count} idle)"
            parts.append(label)
        return ", ".join(parts) or "none"

    vocabulary = Vocabulary(snapshot)
    buildable = [snapshot.actor_name(item) for item in snapshot.available_production
                 if vocabulary.entries.get(item.lower(), Entry(item, "", (), "unit")).category == "building" and not item.lower().endswith("f")]
    trainable = [snapshot.actor_name(item) for item in snapshot.available_production
                 if vocabulary.entries.get(item.lower(), Entry(item, "", (), "unit")).category == "unit"]
    production = ", ".join(
        f"{snapshot.actor_name(str(entry.get('item', '')))} {'ready to place' if float(entry.get('progress', 0)) >= 0.999 else str(round(float(entry.get('progress', 0)) * 100)) + '%'}"
        for entry in snapshot.production[:8]
    ) or "nothing"
    enemy, source = enemy_base(snapshot)
    lines = [
        f"Game: {'Red Alert 2' if snapshot.mod_id == 'ra2' else 'Red Alert (Classic)'}",
        f"Your units: {counted(snapshot.units, idle=True)}",
        f"Your buildings: {counted(snapshot.buildings)}",
        f"Can build: {', '.join(dict.fromkeys(buildable)) or 'nothing'}",
        f"Can train: {', '.join(dict.fromkeys(trainable)) or 'nothing'}",
        f"In production: {production}",
        f"Visible enemies: {counted([*snapshot.visible_enemies, *snapshot.visible_enemy_buildings])}",
        f"Enemy base: {'seen' if source == 'visible' else 'last seen under fog' if source == 'remembered' else 'not found yet'}",
    ]
    return "\n".join(lines)


def intent_messages(text: str, snapshot: GameSnapshot) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": INTENT_PROMPT},
        {"role": "user", "content": f"Vocabulary:\n{vocabulary_context(snapshot)}\n\nPlayer: {json.dumps(text.strip())}"},
    ]


def parse_intent_json(text: str) -> dict[str, Any] | None:
    value = text.strip()
    if value.startswith("```"):
        value = value.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        decoded = json.loads(value[start : end + 1])
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def validate_intent(decoded: dict[str, Any]) -> tuple[str, str, list[Step]] | None:
    """Strictly validate a model intent against ORDER_SCHEMA semantics."""
    intent = str(decoded.get("intent", "")).strip().lower()
    if intent not in {"command", "question", "clarify", "refuse"}:
        return None
    reply = str(decoded.get("reply", "") or "").strip()
    raw_steps = decoded.get("steps", [])
    if not isinstance(raw_steps, list):
        return None
    steps: list[Step] = []
    for raw in raw_steps[:4]:
        if not isinstance(raw, dict):
            return None
        action = str(raw.get("action", "")).strip().lower()
        if action not in INTENT_ACTIONS:
            return None
        try:
            count = int(raw.get("count", 0) or 0)
        except (TypeError, ValueError):
            count = 0
        steps.append(Step(
            action=action,
            units=str(raw.get("units", "") or "")[:60],
            count=max(0, min(MAX_ORDERS, count)),
            item=str(raw.get("item", "") or "")[:60],
            target=str(raw.get("target", "") or "")[:60],
            stance=str(raw.get("stance", "") or "")[:20],
            source="model",
        ))
    if intent == "command" and not steps:
        return None
    return intent, reply, steps


_BROKEN_TEXT = re.compile(r"[{}\[\]`<>]|\\n|\"(intent|mode|steps|action)\"")


def safe_reply(snapshot: GameSnapshot, reply: str, fallback: str) -> str:
    """Only let short, clean natural language reach the player."""
    text = " ".join(reply.split())
    if not text or len(text) > 200 or _BROKEN_TEXT.search(text) or is_repetitive(text):
        return fallback
    humanized = snapshot.humanize_text(text)
    return humanized if humanized.endswith((".", "?", "!")) else humanized + "."


def answer_is_malformed(text: str) -> bool:
    """True for free-text answers that must not be shown (empty, raw JSON, loops)."""
    stripped = text.strip()
    return (
        not stripped
        or len(stripped) > 600
        or stripped.startswith(("{", "["))
        or "```" in stripped
        or bool(re.search(r"\"(intent|mode|steps|commands|answer)\"\s*:", stripped))
        or is_repetitive(stripped)
    )


def status_line(snapshot: GameSnapshot) -> str:
    """A factual, deterministic answer used when a model answer is unusable."""
    units = [unit for unit in snapshot.units if not is_husk(unit) and unit.speed > 0]
    power = snapshot.power_provided - snapshot.power_drained
    enemies = len(snapshot.visible_enemies) + len(snapshot.visible_enemy_buildings)
    return (
        f"You have ${snapshot.cash:,}, power {power:+}, {len(units)} unit{'s' if len(units) != 1 else ''} and "
        f"{len(snapshot.buildings)} building{'s' if len(snapshot.buildings) != 1 else ''}; "
        f"{enemies or 'no'} enem{'ies' if enemies != 1 else 'y'} in sight."
    )


def is_repetitive(text: str) -> bool:
    words = re.findall(r"[a-z0-9']+", text.lower())
    if len(words) < 12:
        return False
    trigrams = [tuple(words[index:index + 3]) for index in range(len(words) - 2)]
    most = max(trigrams.count(trigram) for trigram in set(trigrams))
    return most >= 4 or len(set(words)) / len(words) < 0.3


def interpret_model_intent(text: str, snapshot: GameSnapshot, decoded: dict[str, Any]) -> OrderResult | None:
    validated = validate_intent(decoded)
    if validated is None:
        return None
    intent, reply, steps = validated
    if intent == "question":
        return OrderResult("question", path="model")
    if intent == "refuse":
        category = classify(text)
        default = REFUSAL_TEXT.get(category.split(":", 1)[1], "") if category.startswith("refuse:") else ""
        return OrderResult("refuse", default or safe_reply(snapshot, reply, "I can't do that as a voice order."), path="model")
    if intent == "clarify":
        return OrderResult("clarify", safe_reply(snapshot, reply, "Which units should do what, and where?"), path="model")
    for step in steps:
        if step.action in {"train", "build"} and not step.item and step.units:
            step.item = step.units
            step.units = ""
    return ground_steps(snapshot, steps, path="model")
