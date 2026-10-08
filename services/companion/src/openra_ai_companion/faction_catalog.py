"""Mode-aware faction and unit knowledge for catalog questions.

Two sources are joined:

* the shared editorial catalog (``catalog/factions.json``): stories, roles,
  signature units, counterplay and which game mode implements each faction;
* the live rules digest the game engine posts to ``/v1/factions/live`` for the
  loaded mode: every roster actor with cost, HP, armor, weapons, targets,
  strategic roles and counters, read from the engine's merged rules.

Both are static unit knowledge. Nothing here comes from a match observation,
so catalog answers cannot reveal enemy units or anything hidden by fog of war.
Answers never mention units of a faction that is not implemented in the mode
being discussed.
"""
from __future__ import annotations

import atexit
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
import unicodedata
from typing import Any, Mapping

DIGEST_SCHEMA = "openra-ai.faction-catalog.live/1"
DIGEST_DIRECTORY_ENV = "OPENRA_AI_FACTION_DIGEST_DIR"
MODE_NAMES = {"ra": "Classic", "ra2": "Red Alert 2"}
MODE_WORDS = {
    "ra2": ("red alert 2", "ra2", "ra 2"),
    "ra": ("classic", "world war iii", "world war 3", "ww3", "wwiii"),
}
QUESTION_STARTS = (
    "what", "which", "who", "how", "does", "do", "is", "are", "can", "could", "should", "tell me", "describe",
    "explain", "compare", "list", "show me", "give me", "whats", "what's", "any",
)
ACTION_STARTS = (
    "build", "train", "produce", "make", "attack", "move", "send", "deploy", "sell", "repair", "place", "guard",
    "capture", "use", "harvest", "stop", "cancel", "set", "switch", "retreat", "scout", "go",
)
# Requests addressed to the assistant ("can you build ...") are orders for the planner, not catalog questions.
REQUEST_PHRASES = ("can you", "could you", "would you", "will you", "please", "lets", "let s", "go ahead",
                   "i want you", "i need you")
# A question that names only a faction must ask about the faction itself; strategy advice goes to the planner.
FACTION_INFO_WORDS = ("tell me about", "what is", "who is", "who are", "what are", "describe", "explain", "doctrine",
                      "signature", "strength", "strengths", "weakness", "weaknesses", "counterplay", "playstyle",
                      "play style", "roster", "about", "overview", "summary", "known for")
LIVE_STATE_WORDS = (
    "enemy", "enemies", "opponent", "where", "how many", "my base", "my army", "my units", "right now", "currently",
    "spotted", "visible", "attacking me", "their base",
)
GENERIC_WORDS = {
    "the", "of", "and", "a", "an", "tank", "tanks", "main", "battle", "unit", "units", "air", "defense", "defence",
    "drone", "mobile", "team", "infantry", "vehicle", "missile", "rocket", "ship", "boat", "craft", "site", "system",
    "launcher", "heavy", "light", "armored", "armoured", "strike", "fighter", "gun", "anti", "sam", "uav", "ucav",
    "ifv", "apc", "mbt", "command", "network", "carrier", "assault", "patrol", "frigate", "destroyer", "submarine",
    "helicopter", "gunship", "soldier", "hunter", "vessel", "surface", "coastal", "multiple", "armed", "combined",
    "arms", "national", "guard", "rifle", "rifleman", "specialist", "modular", "system", "interceptor", "plant",
    "yard", "factory", "barracks", "pad", "power", "radar", "dome", "lab", "center", "centre", "headquarters",
    "construction", "refinery", "service", "depot", "wall", "tower", "turret", "bunker", "battery", "support",
    "uncrewed", "unmanned", "ground", "amphibious", "dock", "transport", "attack", "spy", "dog", "engineer",
    "soviet", "allied", "allies", "modern", "original",
}
FACTION_ADJECTIVES = {
    "china": {"chinese"}, "iran": {"iranian"}, "yemen": {"yemeni"}, "saudi arabia": {"saudi"},
    "turkey": {"turkiye", "turkish"}, "turkiye": {"turkey", "turkish"}, "russia": {"russian"},
    "england": {"british", "britain", "english"}, "america": {"american"}, "germany": {"german"},
    "france": {"french"}, "korea": {"korean"}, "cuba": {"cuban"}, "libya": {"libyan"}, "iraq": {"iraqi"},
    "ukraine": {"ukrainian"},
}
CAPABILITIES: dict[str, tuple[tuple[str, ...], str]] = {
    "anti-air": (("anti air", "antiair", "anti-air", "air defense", "air defence", " aa ", "shoot down", "against air",
                  "against aircraft", "hit aircraft", "hits aircraft", "target aircraft", "air cover"), "attack aircraft"),
    "anti-armor": (("anti armor", "anti-armor", "anti tank", "anti-tank", "antitank", "against tanks", "against armor",
                    "kill tanks", "against vehicles"), "counter armor"),
    "artillery": (("artillery", "long range", "long-range", "siege", "indirect"), "provide artillery or siege fire"),
    "scout": (("scout", "recon", "reconnaissance"), "scout"),
    "transport": (("transport", "carry", "carries", "passengers", "airlift"), "transport units"),
    "naval": (("naval", "navy", "ship", "ships", "boat", "boats", "sea"), "fight at sea"),
    "aircraft": (("aircraft", "air unit", "air units", "planes", "helicopter", "helicopters", "jets"), "fly"),
    "anti-infantry": (("anti infantry", "anti-infantry", "against infantry", "kill infantry"), "counter infantry"),
    "engineer": (("engineer", "capture", "repair"), "capture or repair"),
    "defense": (("defense structure", "defensive structure", "static defense", "defenses", "defences", "turret"),
                "defend a base"),
}
COUNTER_OF_WORDS = ("counter", "counters", "good against", "strong against", "effective against", "best against",
                    "used against", "use it for", "use it against")
COUNTER_TO_WORDS = ("what counters", "counter to", "how do i beat", "how to beat", "how do i kill", "how to kill",
                    "how do i stop", "how to stop", "weak against", "weakness", "weaknesses", "vulnerable",
                    "beats the", "beat the", "deal with")
STAT_WORDS = {
    "cost": ("cost", "price", "how much", "credits"),
    "hitPoints": ("hp", "hit points", "health", "durable", "tough"),
    "range": ("range", "how far"),
    "speed": ("speed", "fast", "slow"),
    "armor": ("armor", "armour"),
    "buildTimeSeconds": ("build time", "how long"),
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return " " + re.sub(r"[^a-z0-9]+", " ", text).strip() + " "


def _clause(text: str | None) -> str:
    """Editorial sentences are embedded in longer answers; drop their final period."""
    return (text or "").strip().rstrip(".")


def catalog_candidates(
    env: Mapping[str, str] | None = None,
    executable: str | None = None,
    frozen: bool | None = None,
    module_file: str | None = None,
) -> list[Path]:
    """Where the shared catalog lives in development and installed layouts, in priority order.

    Packaged builds stage it beside the companion's ``bin`` directory:
    Windows ``<root>/bin/openra-ai-companion.exe`` -> ``<root>/catalog/factions.json``;
    macOS ``Contents/Resources/bin/openra-ai-companion`` -> ``Contents/Resources/catalog/factions.json``.
    """
    env = os.environ if env is None else env
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    relative = Path("catalog") / "factions.json"
    paths: list[Path] = []
    if env.get("OPENRA_AI_CATALOG"):
        paths.append(Path(env["OPENRA_AI_CATALOG"]))
    if env.get("OPENRA_AI_ROOT"):
        paths.append(Path(env["OPENRA_AI_ROOT"]) / relative)
    if frozen:
        paths.append(Path(executable or sys.executable).resolve().parent.parent / relative)
    if env.get("OPENRA_AI_ENGINE_DIR"):
        engine = Path(env["OPENRA_AI_ENGINE_DIR"])
        paths += [engine / relative, engine.parent.parent / relative, engine.parent / "OpenRA-AI" / relative]
    paths.append(Path(module_file or __file__).resolve().parents[4] / relative)
    return [path.resolve() for path in paths]


def locate_catalog(**kwargs: Any) -> Path | None:
    return next((path for path in catalog_candidates(**kwargs) if path.is_file()), None)


@dataclass
class CatalogAnswer:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _Unit:
    """One roster actor in one mode, joined with its editorial entry when curated."""
    mode: str
    actor: str
    name: str
    faction_key: str
    faction_name: str
    live: dict[str, Any] | None
    editorial: dict[str, Any] | None

    @property
    def key(self) -> tuple[str, str]:
        return self.mode, self.actor.casefold()

    def fact(self) -> dict[str, Any]:
        live = self.live or {}
        fact = {
            "name": self.name, "actor": self.actor, "faction": self.faction_name, "mode": MODE_NAMES.get(self.mode, self.mode),
            "domain": live.get("domain"), "role": (self.editorial or {}).get("role") or live.get("role"),
        }
        for key in ("cost", "buildTimeSeconds", "hitPoints", "armor", "speed", "sightCells", "targets", "antiAir",
                    "antiGround", "roles", "counters", "prerequisites", "description", "exclusive", "url"):
            if live.get(key) not in (None, [], ""):
                fact[key] = live[key]
        if live.get("weapons"):
            fact["weapons"] = [{k: w.get(k) for k in ("name", "rangeCells", "minRangeCells", "damage", "burst", "hits", "antiAir")}
                               for w in live["weapons"]]
        if self.editorial:
            fact.update({"strengths": self.editorial.get("strengths"), "counterplay": self.editorial.get("counterplay"),
                         "story": self.editorial.get("story"), "signature": True})
        fact["rules_loaded"] = self.live is not None and bool(live.get("rulesLoaded", True))
        return {k: v for k, v in fact.items() if v not in (None, "")}


class FactionKnowledge:
    """Thread-safe store of the catalog plus the latest live digest per mode."""

    def __init__(self, catalog: dict | None = None, catalog_path: Path | None = None, digest_directory: Path | None = None):
        self.catalog = catalog
        self.catalog_path = catalog_path
        self._digests: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._last_mode: str | None = None
        self._digest_directory = digest_directory
        if digest_directory is not None:
            self._read_digest_directory(digest_directory)

    @classmethod
    def load(cls, **locate: Any) -> "FactionKnowledge":
        path = locate_catalog(**locate)
        catalog = None
        if path is not None:
            try:
                catalog = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                catalog, path = None, None
        shared = os.environ.get(DIGEST_DIRECTORY_ENV)
        return cls(catalog, path, Path(shared) if shared else None)

    # ----- live digest -----------------------------------------------------------------------
    def update_live(self, digest: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(digest, Mapping) or digest.get("schema") != DIGEST_SCHEMA:
            raise ValueError("unsupported faction catalog digest")
        mode = str(digest.get("mode") or "")
        if not re.fullmatch(r"[a-z0-9-]+", mode) or not isinstance(digest.get("factions"), list):
            raise ValueError("faction catalog digest requires a mode and factions")
        clean = json.loads(json.dumps(digest))
        with self._lock:
            self._digests[mode] = clean
            self._last_mode = mode
            self._share(mode, clean)
        return {"accepted": True, "mode": mode, "factions": len(clean["factions"])}

    def _share(self, mode: str, digest: dict) -> None:
        """Let the game-tool MCP child process read the same digest (it inherits the environment)."""
        if self._digest_directory is None:
            self._digest_directory = Path(tempfile.mkdtemp(prefix="openra-ai-factions-"))
            atexit.register(shutil.rmtree, self._digest_directory, True)
            os.environ[DIGEST_DIRECTORY_ENV] = str(self._digest_directory)
        target = self._digest_directory / f"{mode}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(digest), encoding="utf-8")
        temporary.replace(target)

    def _read_digest_directory(self, directory: Path) -> None:
        for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
            try:
                digest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if digest.get("schema") == DIGEST_SCHEMA and digest.get("mode"):
                self._digests[digest["mode"]] = digest
                self._last_mode = digest["mode"]

    def digest(self, mode: str) -> dict | None:
        with self._lock:
            return self._digests.get(mode)

    @property
    def last_mode(self) -> str | None:
        return self._last_mode

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "catalog": str(self.catalog_path) if self.catalog_path else None,
                "catalog_revision": (self.catalog or {}).get("revision"),
                "live_modes": {mode: {"source": d.get("source"), "factions": len(d.get("factions", [])),
                                      "catalog_revision": d.get("catalogRevision")}
                               for mode, d in self._digests.items()},
            }

    # ----- catalog views ---------------------------------------------------------------------
    def _catalog_factions(self) -> list[dict]:
        return list((self.catalog or {}).get("factions", []))

    def _catalog_units(self) -> dict[str, dict]:
        return {unit["id"]: unit for unit in (self.catalog or {}).get("units", [])}

    @staticmethod
    def _implemented(faction: dict, mode: str) -> bool:
        return (faction.get("variants", {}).get(mode) or {}).get("status") == "implemented"

    def _link(self, kind: str, item_id: str, mode: str) -> str:
        links = {"origin": "https://rtsai.net", "faction": "/factions/{factionId}?mode={mode}",
                 "unit": "/units/{unitId}?mode={mode}", **((self.catalog or {}).get("links") or {})}
        placeholder = "{factionId}" if kind == "faction" else "{unitId}"
        return links["origin"].rstrip("/") + links[kind].replace(placeholder, item_id).replace("{mode}", mode)

    def factions(self, mode: str) -> list[dict[str, Any]]:
        """Factions available in ``mode``: live digest entries, else the catalog's implemented factions."""
        digest = self.digest(mode)
        catalog = {f["id"]: f for f in self._catalog_factions()}
        result = []
        if digest is not None:
            for entry in digest["factions"]:
                editorial = catalog.get(entry.get("catalogId") or "")
                result.append({"key": entry.get("catalogId") or entry.get("internalName"), "name": entry.get("name"),
                               "kind": entry.get("kind"), "availability": entry.get("availability"), "live": entry,
                               "editorial": editorial, "internal": entry.get("internalName")})
        else:
            for faction in catalog.values():
                if self._implemented(faction, mode):
                    result.append({"key": faction["id"], "name": faction["name"], "kind": "modern", "availability": "catalog",
                                   "live": None, "editorial": faction, "internal": None})
        return result

    def other_mode_factions(self, mode: str) -> list[dict]:
        return [f for f in self._catalog_factions() if not self._implemented(f, mode)]

    def units(self, mode: str) -> list[_Unit]:
        catalog_units = self._catalog_units()
        by_actor: dict[str, dict] = {}
        for unit in catalog_units.values():
            actor = (unit.get("variants", {}).get(mode) or {}).get("actorId")
            if actor:
                by_actor[actor.casefold()] = unit
        units: list[_Unit] = []
        seen: set[tuple[str, str]] = set()
        for faction in self.factions(mode):
            live_roster = (faction["live"] or {}).get("roster") or []
            for entry in live_roster:
                editorial = catalog_units.get(entry.get("catalogUnitId") or "") or by_actor.get(str(entry.get("actor")).casefold())
                unit = _Unit(mode, str(entry.get("actor")), str(entry.get("name") or (editorial or {}).get("name") or entry.get("actor")),
                             faction["key"], faction["name"], entry, editorial)
                if (unit.key, faction["key"]) not in seen:
                    seen.add((unit.key, faction["key"]))
                    units.append(unit)
            if faction["live"] is None and faction["editorial"]:
                for unit_id in faction["editorial"].get("unitIds", []):
                    editorial = catalog_units.get(unit_id)
                    actor = ((editorial or {}).get("variants", {}).get(mode) or {}).get("actorId")
                    if editorial and actor:
                        units.append(_Unit(mode, actor, editorial["name"], faction["key"], faction["name"], None, editorial))
        return units

    def other_mode_units(self, mode: str) -> list[dict]:
        """Curated units whose faction is not available in ``mode`` (named only to explain their absence)."""
        other = {f["id"]: f for f in self.other_mode_factions(mode)}
        return [u for u in self._catalog_units().values() if u.get("factionId") in other]

    # ----- matching --------------------------------------------------------------------------
    def _faction_words(self) -> set[str]:
        """Faction names and adjectives never identify a single unit ("Yemeni" names several)."""
        words = set().union(*FACTION_ADJECTIVES.values(), FACTION_ADJECTIVES)
        names = [f.get("name", "") for f in self._catalog_factions()]
        with self._lock:
            names += [entry.get("name") or "" for digest in self._digests.values() for entry in digest.get("factions", [])]
        for name in names:
            words |= set(normalize(name).split())
        return words

    @staticmethod
    def _unit_aliases(unit: _Unit, excluded: set[str]) -> list[str]:
        names = {unit.name, unit.actor}
        if unit.editorial:
            names |= {unit.editorial.get("name", ""), unit.editorial.get("id", "")}
        aliases = []
        for name in filter(None, names):
            normal = normalize(name).strip()
            aliases.append(normal)
            aliases += [word for word in normal.split()
                        if len(word) >= 3 and word not in GENERIC_WORDS and word not in excluded and not word.isdigit()]
        return sorted(set(aliases), key=len, reverse=True)

    @staticmethod
    def _faction_aliases(name: str, key: str | None = None, internal: str | None = None) -> list[str]:
        normal = normalize(name).strip()
        aliases = {normal, normalize(key or "").strip(), normalize(internal or "").strip()}
        aliases |= {word for word in normal.split() if len(word) >= 4}
        for base, words in FACTION_ADJECTIVES.items():
            if base in aliases:
                aliases |= words
        return sorted({a for a in aliases if a}, key=len, reverse=True)

    def _match_units(self, text: str, mode: str) -> list[_Unit]:
        matches: list[tuple[int, _Unit]] = []
        excluded = self._faction_words()
        for unit in self.units(mode):
            best = max((len(alias) for alias in self._unit_aliases(unit, excluded) if f" {alias} " in text), default=0)
            if best:
                matches.append((best, unit))
        if not matches:
            return []
        top = max(score for score, _ in matches)
        # Keep the strongest reference plus any other units named in full.
        chosen = [unit for score, unit in matches if score == top or score >= 8]
        unique: dict[tuple[str, str], _Unit] = {}
        for unit in chosen:
            unique.setdefault(unit.key, unit)
        return list(unique.values())

    def _match_factions(self, text: str, mode: str) -> list[dict]:
        found = []
        for faction in self.factions(mode):
            aliases = self._faction_aliases(faction["name"] or "", faction["key"], faction.get("internal"))
            if any(f" {alias} " in text for alias in aliases):
                found.append(faction)
        return found

    def _match_other_mode(self, text: str, mode: str) -> tuple[list[dict], list[dict]]:
        factions = [f for f in self.other_mode_factions(mode)
                    if any(f" {alias} " in text for alias in self._faction_aliases(f["name"], f["id"]))]
        units = []
        for unit in self.other_mode_units(mode):
            normal = normalize(unit["name"]).strip()
            words = [w for w in normal.split() if len(w) >= 3 and w not in GENERIC_WORDS and w not in self._faction_words()]
            if f" {normal} " in text or f" {unit['id']} " in text or any(f" {w} " in text for w in words):
                units.append(unit)
        return factions, units

    @staticmethod
    def _requested_mode(text: str, current: str) -> str:
        for mode, words in MODE_WORDS.items():
            if any(f" {normalize(word).strip()} " in text for word in words):
                return mode
        return current

    # ----- answers ---------------------------------------------------------------------------
    @staticmethod
    def is_catalog_question(question: str) -> bool:
        text = normalize(question)
        stripped = text.strip()
        if any(stripped.startswith(verb + " ") or stripped == verb for verb in ACTION_STARTS):
            return False
        if any(f" {normalize(word).strip()} " in text for word in LIVE_STATE_WORDS + REQUEST_PHRASES):
            return False
        return question.strip().endswith("?") or any(stripped.startswith(normalize(start).strip()) for start in QUESTION_STARTS)

    def answer(self, question: str, mode: str | None) -> CatalogAnswer | None:
        """A grounded answer for a faction/unit catalog question, or None when the question is something else."""
        if self.catalog is None and not self._digests:
            return None
        if not self.is_catalog_question(question):
            return None
        text = normalize(question)
        current = mode if mode in MODE_NAMES else (self._last_mode or "ra")
        mode = self._requested_mode(text, current)
        units = self._match_units(text, mode)
        factions = self._match_factions(text, mode)
        other_factions, other_units = self._match_other_mode(text, mode)
        capability = next((name for name, (words, _) in CAPABILITIES.items()
                           if any(word in text if word.startswith(" ") else f" {normalize(word).strip()} " in text for word in words)), None)
        mode_name = MODE_NAMES.get(mode, mode)
        metadata: dict[str, Any] = {"mode": mode, "source": "catalog+rules" if self.digest(mode) else "catalog"}

        # Only answer questions that actually name a faction or unit from either mode.
        if not (units or factions or other_factions or other_units):
            return None
        # "Should I build Qilins?" asks for advice about the live match; leave it to the planner.
        asks_facts = capability or any(normalize(w).strip() in text for w in COUNTER_OF_WORDS + COUNTER_TO_WORDS) or \
            any(f" {normalize(w).strip()} " in text for words in STAT_WORDS.values() for w in words)
        if " should " in text and not asks_facts:
            return None

        if not units and not factions:
            names = ", ".join(sorted({u["name"] for u in other_units} | {f["name"] for f in other_factions}))
            owners = sorted({f["name"] for f in other_factions} |
                            {self._faction_name(u.get("factionId")) for u in other_units})
            elsewhere = sorted({MODE_NAMES.get(m, m) for f in self._catalog_factions() if f["name"] in owners
                                for m, v in f.get("variants", {}).items() if (v or {}).get("status") == "implemented"})
            where = f" It is available in {' and '.join(elsewhere)}." if elsewhere else ""
            metadata.update(factions=owners, units=[u["id"] for u in other_units], unavailable=True)
            if other_units:
                unit_names = ", ".join(sorted({u["name"] for u in other_units}))
                text = f"{unit_names} belongs to {', '.join(owners)}, which isn't available in {mode_name} mode.{where}"
            else:
                text = f"{names} isn't available in {mode_name} mode yet.{where}"
            return CatalogAnswer(text, metadata)

        if factions and units:
            # "Which China unit can transport?" names a faction; a unit that merely shares a word belongs elsewhere.
            keys = {f["key"] for f in factions}
            units = [u for u in units if u.faction_key in keys]
        facts = [unit.fact() for unit in units]
        metadata.update(units=[u.actor for u in units], factions=[f["key"] for f in factions])
        if capability and factions and not units:
            result = self._capability_answer(factions, capability, mode, metadata)
        elif units:
            result = self._unit_answer(units, text, mode, metadata, facts)
        elif " should " in text or not any(f" {normalize(word).strip()} " in text for word in FACTION_INFO_WORDS):
            return None
        else:
            result = self._faction_answer(factions, mode, metadata)
        absent = sorted({f["name"] for f in other_factions} | {self._faction_name(u.get("factionId")) for u in other_units})
        if absent:
            result.text += f" ({', '.join(absent)} {'is' if len(absent) == 1 else 'are'} not available in {mode_name}.)"
            metadata["unavailable_here"] = absent
        return result

    def _faction_name(self, faction_id: str | None) -> str:
        return next((f["name"] for f in self._catalog_factions() if f["id"] == faction_id), faction_id or "")

    def _capability_answer(self, factions: list[dict], capability: str, mode: str, metadata: dict) -> CatalogAnswer:
        label = CAPABILITIES[capability][1]
        mode_name = MODE_NAMES.get(mode, mode)
        lines = []
        for faction in factions:
            roster = [u for u in self.units(mode) if u.faction_key == faction["key"]]
            if not any(u.live for u in roster):
                lines.append(f"{faction['name']} ({mode_name}): live rules aren't loaded yet, so I can't list its roster statistics. "
                             "Open the Faction Catalog or start a match to share them.")
                continue
            matches = [u for u in roster if u.live and self._has_capability(u.live, capability)]
            if not matches:
                lines.append(f"In {mode_name}, none of {faction['name']}'s roster entries can {label} in the loaded rules.")
                continue
            described = [self._short(u) for u in matches]
            mobile = [u for u in matches if (u.live or {}).get("domain") not in {"Buildings", "Defenses"}]
            summary = f"In {mode_name}, {faction['name']} units that can {label}: " + "; ".join(described) + "."
            if capability == "anti-air" and not mobile:
                summary += " None of its mobile units can target aircraft."
            lines.append(summary)
        metadata["capability"] = capability
        metadata["units"] = [u.actor for f in factions for u in self.units(mode)
                             if u.faction_key == f["key"] and u.live and self._has_capability(u.live, capability)]
        return CatalogAnswer(" ".join(lines), metadata)

    @staticmethod
    def _has_capability(live: dict, capability: str) -> bool:
        roles = set(live.get("roles") or [])
        counters = set(live.get("counters") or [])
        domain = live.get("domain")
        if capability == "anti-air":
            return bool(live.get("antiAir"))
        if capability == "anti-armor":
            return bool({"anti-armor", "anti-tank"} & roles or {"armor", "vehicle"} & counters)
        if capability == "artillery":
            return bool({"artillery", "indirect-fire", "siege"} & roles)
        if capability == "scout":
            return bool({"scout", "reconnaissance", "recon"} & roles)
        if capability == "transport":
            return bool(live.get("passengers")) and domain not in {"Buildings", "Defenses"} or "transport" in roles
        if capability == "naval":
            return domain == "Navy"
        if capability == "aircraft":
            return domain == "Aircraft"
        if capability == "anti-infantry":
            return "infantry" in counters or "anti-infantry" in roles
        if capability == "engineer":
            return bool({"engineer", "capture", "repair"} & roles)
        if capability == "defense":
            return domain == "Defenses"
        return False

    @staticmethod
    def _short(unit: _Unit) -> str:
        live = unit.live or {}
        bits = [unit.name]
        extra = []
        if live.get("domain"):
            extra.append(live["domain"].rstrip("s").lower() if live["domain"] not in {"Infantry", "Aircraft"} else live["domain"].lower())
        weapon = max(live.get("weapons") or [], key=lambda w: w.get("rangeCells", 0), default=None)
        if weapon:
            extra.append(f"range {weapon['rangeCells']:g} cells")
        if live.get("cost"):
            extra.append(f"${live['cost']:,}")
        return bits[0] + (f" ({', '.join(extra)})" if extra else "")

    def _unit_answer(self, units: list[_Unit], text: str, mode: str, metadata: dict, facts: list[dict]) -> CatalogAnswer:
        mode_name = MODE_NAMES.get(mode, mode)
        counter_to = any(normalize(word).strip() in text for word in COUNTER_TO_WORDS)
        counter_of = not counter_to and any(f" {normalize(word).strip()} " in text for word in COUNTER_OF_WORDS)
        stats = [key for key, words in STAT_WORDS.items() if any(f" {normalize(w).strip()} " in text for w in words)]
        sentences = []
        for unit in units:
            live = unit.live or {}
            editorial = unit.editorial or {}
            head = f"{unit.name} ({unit.faction_name}, {mode_name})"
            if not live:
                role = editorial.get("role")
                sentences.append(f"{head}: {role}. Live rules aren't loaded yet, so I can't quote its statistics."
                                 + (f" {editorial.get('strengths')}" if editorial.get("strengths") else ""))
                continue
            if counter_to:
                parts = [f"Countering the {unit.name} ({mode_name})"]
                if editorial.get("counterplay"):
                    parts.append(f"catalog advice: {_clause(editorial['counterplay'])}")
                if live.get("weapons") and not live.get("antiAir"):
                    parts.append("its weapons cannot target aircraft")
                elif not live.get("weapons"):
                    parts.append("it is unarmed")
                if live.get("armor"):
                    parts.append(f"it has {live['armor']} armor and {live.get('hitPoints', 0):,} HP")
                ranges = [w for w in live.get("weapons") or [] if w.get("minRangeCells")]
                if ranges:
                    parts.append(f"it cannot fire inside {ranges[0]['minRangeCells']:g} cells")
                sentences.append(": ".join(parts[:1]) + (" — " + "; ".join(parts[1:]) if len(parts) > 1 else "") + ".")
            elif counter_of:
                counters = [c.replace("-", " ") for c in live.get("counters") or []]
                roles = [r.replace("-", " ") for r in live.get("roles") or []]
                reach = (live.get("targets") or "nothing").lower()
                if counters:
                    sentence = f"{head} is built to counter {', '.join(counters)}; it attacks {reach}"
                else:
                    sentence = f"{head} has no counter tags in the loaded rules"
                    if roles:
                        sentence += f"; its role is {', '.join(roles)}"
                    sentence += f"; it attacks {reach}"
                if editorial.get("strengths"):
                    sentence += f". Catalog: {_clause(editorial['strengths'])}"
                if editorial.get("counterplay"):
                    sentence += f". Watch out: {_clause(editorial['counterplay'])}"
                sentences.append(sentence + ".")
            else:
                sentences.append(self._describe(unit, head, stats))
        metadata["facts"] = facts
        return CatalogAnswer(" ".join(sentences), metadata)

    @staticmethod
    def _describe(unit: _Unit, head: str, stats: list[str]) -> str:
        live = unit.live or {}
        editorial = unit.editorial or {}
        pieces = []
        role = editorial.get("role") or live.get("role")
        if role:
            pieces.append(role)
        if live.get("cost"):
            pieces.append(f"costs ${live['cost']:,}")
        if live.get("hitPoints"):
            pieces.append(f"{live['hitPoints']:,} HP" + (f", {live['armor']} armor" if live.get("armor") else ""))
        if live.get("speed") and ("speed" in stats or not stats):
            pieces.append(f"speed {live['speed']}")
        weapons = live.get("weapons") or []
        if weapons:
            descriptions = [f"{w['name']} (range {w['rangeCells']:g} cells, hits {', '.join(w.get('hits') or [])})" for w in weapons[:2]]
            pieces.append("armed with " + "; ".join(descriptions))
        else:
            pieces.append("unarmed")
        if live.get("prerequisites") and ("buildTimeSeconds" in stats or not stats):
            pieces.append("requires " + ", ".join(live["prerequisites"]))
        if live.get("buildTimeSeconds") and "buildTimeSeconds" in stats:
            pieces.append(f"builds in {live['buildTimeSeconds']:g}s at normal speed")
        return f"{head}: " + "; ".join(pieces) + "."

    def _faction_answer(self, factions: list[dict], mode: str, metadata: dict) -> CatalogAnswer:
        mode_name = MODE_NAMES.get(mode, mode)
        sentences = []
        for faction in factions:
            editorial = faction["editorial"] or {}
            live = faction["live"] or {}
            title = f"{faction['name']}" + (f" — {editorial['title']}" if editorial.get("title") else "")
            parts = [f"{title} ({mode_name})"]
            if live.get("doctrine"):
                parts.append(f"Doctrine: {live['doctrine']}")
            if editorial.get("strengths"):
                parts.append(f"Strengths: {_clause(editorial['strengths'])}")
            if editorial.get("counterplay"):
                parts.append(f"Counterplay: {_clause(editorial['counterplay'])}")
            signature = [u.name for u in self.units(mode) if u.faction_key == faction["key"] and u.editorial]
            if signature:
                parts.append("Signature units: " + ", ".join(signature))
            elif live.get("description"):
                parts.append(_clause(live["description"].replace("\n", "; ")))
            if faction.get("availability") == "disabled":
                parts.append("Installed but not enabled in the current experience")
            sentences.append(". ".join(parts) + ".")
            metadata.setdefault("links", []).append(self._link("faction", faction["key"], mode) if editorial else None)
        return CatalogAnswer(" ".join(sentences), metadata)

    # ----- LLM context and tools ---------------------------------------------------------------
    def context(self, question: str, mode: str | None) -> dict[str, Any] | None:
        """Compact, mode-filtered facts about the factions/units a question names, for model prompts."""
        text = normalize(question)
        mode = self._requested_mode(text, mode if mode in MODE_NAMES else (self._last_mode or "ra"))
        units = self._match_units(text, mode)
        factions = self._match_factions(text, mode)
        if not units and not factions:
            return None
        return {
            "mode": MODE_NAMES.get(mode, mode),
            "rule": "Static catalog and rules knowledge only; never evidence about the current match.",
            "units": [u.fact() for u in units][:6],
            "factions": [self._faction_summary(f, mode) for f in factions][:3],
            "not_in_this_mode": [f["name"] for f in self.other_mode_factions(mode)],
        }

    def _faction_summary(self, faction: dict, mode: str) -> dict[str, Any]:
        editorial = faction["editorial"] or {}
        live = faction["live"] or {}
        roster = [u for u in self.units(mode) if u.faction_key == faction["key"]]
        return {k: v for k, v in {
            "name": faction["name"], "title": editorial.get("title"), "doctrine": live.get("doctrine"),
            "availability": faction.get("availability"), "strengths": editorial.get("strengths"),
            "counterplay": editorial.get("counterplay"),
            "signature_units": [u.name for u in roster if u.editorial],
            "roster": [{"name": u.name, "domain": (u.live or {}).get("domain"), "targets": (u.live or {}).get("targets"),
                        "roles": (u.live or {}).get("roles")} for u in roster if u.live],
            "url": self._link("faction", faction["key"], mode) if editorial else None,
        }.items() if v not in (None, [], "")}

    def lookup(self, query: str, mode: str | None) -> dict[str, Any]:
        """Game-tool view: facts for the named factions/units, or the mode's faction overview."""
        mode = self._requested_mode(normalize(query), mode if mode in MODE_NAMES else (self._last_mode or "ra"))
        found = self.context(query, mode) if query.strip() else None
        result = found or {
            "mode": MODE_NAMES.get(mode, mode),
            "factions": [{"name": f["name"], "kind": f["kind"], "availability": f["availability"],
                          "signature_units": [u.name for u in self.units(mode) if u.faction_key == f["key"] and u.editorial]}
                         for f in self.factions(mode)],
            "not_in_this_mode": [f["name"] for f in self.other_mode_factions(mode)],
        }
        result["live_rules"] = self.digest(mode) is not None
        answer = self.answer(query, mode) if query.strip() else None
        if answer is not None:
            result["answer"] = answer.text
        return result
