#!/usr/bin/env python3
"""Private native Saudi Arabia / Yemen production, combat, range and art checks.

Isolated support profiles and loopback ports only. Production uses a prebuilt
economy, fast build and 50,000 test credits; technology gates stay active.
Combat/ability checks are paired comparisons in one match (identical actors,
one difference). Visual mode captures real rendered game pixels.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time

from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.models import ActionCommand
import ra2_red_sea_assets as art

SPEC = importlib.util.spec_from_file_location("turkey_fixture", Path(__file__).with_name("validate-ra2-turkey.py"))
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

SOVIET_BUILDINGS = (("gacnst", "nacnst"), ("gaweap", "naweap"), ("gapowr", "napowr"), ("garefn", "narefn"),
                    ("gaairc", "naradr"), ("gapile", "nahand"), ("gatech", "natech"), ("gayard", "nayard"))
FACTIONS = {
    "saudi": {
        "units": art.SAUDI_UNITS, "defenses": art.SAUDI_DEFENSES, "soviet": False,
        # Stock Allied combat choices that the Saudi pack replaces, and other modern packs.
        "forbidden": {"e1", "mtnk", "fv", "sref", "mgtk", "shad", "orca", "dest", "aegis", "dlph", "carrier",
                      "gapill", "nasam", "atesla", "r2bozkir", "r2qilin", "r2karrar", "r2technical"},
        "vehicles": ("r2m1a2s", "r2sads", "r2caesar", "r2bradley"),
        "cargo": ("r2sang", "r2bradley"), "ships": ("r2sadiq", "r2riyadh", "r2jubail"),
        "air_only": ("r2sads",), "both_domains": ("r2f15sa",),
    },
    "yemen": {
        "units": art.YEMEN_UNITS, "defenses": art.YEMEN_DEFENSES, "soviet": True,
        "forbidden": {"e2", "flakt", "shk", "ivan", "yuri", "dron", "htnk", "apoc", "zep", "sub", "hyd", "sqd",
                      "nalasr", "naflak", "tesla", "r2karrar", "r2qilin", "r2bozkir", "r2m1a2s"},
        "vehicles": ("r2technical", "r2ytechrr", "r2yzu", "r2ymlr"),
        # The native Flak Track stays Yemen's infantry carrier.
        "cargo": ("r2ymr", "htk"), "ships": ("r2mokha", "r2hodeidah", "r2sahaab"),
        "air_only": ("r2yzu",), "both_domains": (),
    },
}
# Shooter, victim, declared range (cells), v row, aircraft (attack movement allowed).
EDGES = {
    "saudi": (("r2saat", "mtnk", 8, 20, False), ("r2caesar", "mtnk", 13, 20, False),
              ("r2satow", "mtnk", 9, 20, False), ("r2m1a2s", "mtnk", 6, 20, False),
              ("r2sapatriot", "jumpjet", 14, 50, False), ("r2sads", "jumpjet", 12, 50, False),
              ("r2riyadh", "lcrf", 10, 104, False), ("r2sadiq", "lcrf", 6, 104, False),
              ("r2f15sa", "mtnk", 8, 70, True), ("r2ah64sa", "mtnk", 7, 70, True)),
    "yemen": (("r2yrpg", "mtnk", 4.5, 20, False), ("r2ymlr", "mtnk", 13, 20, False),
              ("r2ycoastal", "lcrf", 12, 104, False), ("r2ytechrr", "mtnk", 6, 20, False),
              ("r2yzu", "jumpjet", 8, 50, False), ("r2yzunest", "jumpjet", 9, 50, False),
              ("r2hodeidah", "lcrf", 10, 104, False), ("r2technical", "e1", 5.5, 20, False)),
}


def cell_distance(v, du, dv):
    """True world distance of an MPos offset (U steps 1448, V steps 724)."""
    return math.hypot((2 * du + (v + dv) % 2 - v % 2) * 724, dv * 724) / 1024


def edge_offset(v, declared):
    best = None
    for du in range(0, 12):
        for dv in range(0, 30):
            fraction = cell_distance(v, du, dv) / declared
            if .905 <= fraction <= .965 and (best is None or abs(fraction - .935) < best[0]):
                best = (abs(fraction - .935), du, dv)
    assert best, declared
    return best[1], best[2]


def actor(name, kind, u, v, owner="Multi0", extra=""):
    x, y = u + (v + 1) // 2, v // 2 - u
    return f"\t{name}: {kind}\n\t\tOwner: {owner}\n\t\tLocation: {x},{y}\n{extra}"


def cell(u, v):
    """Bridge observations and move orders use map (MPos) coordinates."""
    return u, v


def base_fixture(resources, profile, country):
    target = BASE.fixture(resources, profile)
    text = (target / "map.yaml").read_text().replace("Faction: turkey", "Faction: " + country)
    if FACTIONS[country]["soviet"]:
        for old, new in SOVIET_BUILDINGS:
            text = text.replace(": " + old + "\n", ": " + new + "\n")
    power = "napowr" if FACTIONS[country]["soviet"] else "gapowr"
    # Extra real power plants keep defenses powered throughout.
    text = text.replace("Rules:\n", "".join(actor("RangePower" + str(i), power, 5 + i * 3, 88) for i in range(3)) + "Rules:\n")
    return target, text


def fixture(resources, profile, country, mode, scene="infantry", facing=640, color="E04444", terrain="temperate"):
    target, text = base_fixture(resources, profile, country)
    spec = FACTIONS[country]
    targets, lua, actors = {}, [], ""
    if mode == "production":
        pass
    elif mode == "edges":
        edges = {}
        for i, (kind, victim, declared, v, aircraft) in enumerate(EDGES[country]):
            u = 8 + (i % 5) * 22
            du, dv = edge_offset(v, declared)
            actors += actor("Edge" + str(i), kind, u, v) + actor("Target" + str(i), victim, u + du, v + dv, "Multi1")
            spotter = FACTIONS[country]["ships"][0] if v + dv >= 100 else spec["units"][0]
            actors += actor("Spotter" + str(i), spotter, u + du + 1, v + dv)
            lua += [f'Edge{i}.Stance = "HoldFire"', f'Target{i}.Stance = "HoldFire"', f'Spotter{i}.Stance = "HoldFire"']
            key = kind + ("-aa" if victim == "jumpjet" else "")
            targets[key] = cell(u + du, v + dv)
            distance = cell_distance(v, du, dv)
            edges[key] = {"range_cells": round(distance, 3), "declared_range": declared,
                          "range_fraction": round(distance / declared, 3), "allow_move": aircraft}
        attack = " ".join(f"Edge{i}.Attack(Target{i}, {'true' if e[4] else 'false'})" for i, e in enumerate(EDGES[country]))
        lua.append(f"Trigger.AfterDelay(40, function() {attack} end)")
        text += victims({e[1] for e in EDGES[country]})
        targets["_edges"] = edges
    elif mode == "combat":
        actors, lua, targets = combat_scene(country)
        text += victims({"mtnk", "e1", "jumpjet", "lcrf", "gapowr", "napowr", "htnk"})
    elif mode == "visual":
        actors, focus = visual_scene(country, scene, facing)
        lua.append("Camera.Position = " + focus + ".CenterPosition")
        text = text.replace("Color: E04444", "Color: " + color)
        if terrain == "snow":
            text = text.replace("Tileset: TEMPERATE", "Tileset: SNOW")
        # Static art review: park aircraft instead of returning to a factory.
        text += "\tr2f15sa:\n\t\tAircraft:\n\t\t\tIdleBehavior: None\n\t\t\tIdleSpeed: 0\n"
        text += "\tr2samad:\n\t\tAircraft:\n\t\t\tIdleBehavior: None\n"
    if mode in ("edges", "combat"):
        text = text.replace("\tPlayer:\n", "\tPlayer:\n\t\tModularBot@range:\n\t\t\tName: ra2-bot-normal\n\t\t\tType: range-target\n")
        # Lobby fog is the real switch (a map-rule "FogEnabled" is ignored), so
        # vision can never shorten a range or damage check here.
        text = text.replace("\t\tShroud:\n\t\t\tFogEnabled: false\n",
                            "\t\tShroud:\n\t\t\tFogCheckboxEnabled: false\n\t\t\tFogCheckboxLocked: true\n")
    text = text.replace("Rules:\n", actors + "Rules:\n")
    (target / "map.yaml").write_text(text)
    script = 'WorldLoaded = function()\n  Player.GetPlayer("Multi0").Cash = 50000\n'
    script += "\n".join("  " + line for line in lua) + "\nend\n"
    (target / "review.lua").write_text(script)
    return targets


def victims(kinds):
    text = ""
    for kind in sorted(kinds):
        text += f"\t{kind}:\n\t\tHealth:\n\t\t\tHP: 10000\n"
        if kind == "e1":
            text += "\t\t-TakeCover:\n"
    return text


def combat_scene(country):
    """Every armed entry vs a durable target, plus paired ability comparisons.

    Each comparison uses identical actors and targets that differ in exactly
    one condition (laser mark, brace, guidance, link, support ship, ...).
    """
    spec = FACTIONS[country]
    armed = [a for a in spec["units"] + spec["defenses"] if a not in ("r2sajtac", "r2jubail", "r2yspot", "r2mokha", "r2sahaab")]
    actors, lua, targets, deploys = "", [], {}, []
    naval_slot = ground_slot = 0
    for i, kind in enumerate(armed):
        if kind in spec["ships"]:
            u, v = 8 + naval_slot * 16, 104
            naval_slot += 1
            prey = "lcrf"
        else:
            u, v = 8 + (ground_slot % 6) * 20, 12 + (ground_slot // 6) * 18
            ground_slot += 1
            prey = "jumpjet" if kind in spec["air_only"] + ("r2sapatriot", "r2yzunest") else "e1" if kind in (
                "r2sang", "r2falcon", "r2ymr", "r2technical", "r2saguard", "r2ybunker") else "mtnk"
        du, dv = (3, 6) if kind in ("r2caesar", "r2ymlr") else (2, 4)
        if kind == "r2wadighost":
            prey, du, dv = "napowr", 1, 3
        actors += actor("A" + str(i), kind, u, v) + actor("T" + str(i), prey, u + du, v + dv, "Multi1")
        targets[kind] = cell(u + du, v + dv)
        lua.append(f'A{i}.Stance = "HoldFire"')
        if prey != "napowr":
            lua.append(f'T{i}.Stance = "HoldFire"')
    attacks = " ".join(f"A{i}.Attack(T{i})" for i in range(len(armed)))
    if country == "saudi":
        pairs = [
            # Laser guidance: identical ATGM teams and tanks; only one tank is lased.
            ("Jtac", "r2sajtac", 18, 72, "Multi0"), ("Lased", "r2saat", 20, 72, "Multi0"),
            ("LasedTarget", "mtnk", 22, 77, "Multi1"), ("Unlased", "r2saat", 60, 72, "Multi0"),
            ("UnlasedTarget", "mtnk", 62, 77, "Multi1"),
            # Brace: identical Guard riflemen; one deployed through the native order.
            ("Braced", "r2sang", 90, 72, "Multi0"), ("BracedTarget", "e1", 92, 76, "Multi1"),
            ("Loose", "r2sang", 110, 72, "Multi0"), ("LooseTarget", "e1", 112, 76, "Multi1"),
            # Interceptor magazine: identical enemy missile craft vs frigate and
            # support ship (same Heavy armor; HP loss compared in points).
            ("Shooter1", "r2hodeidah", 70, 106, "Multi1"), ("Frigate", "r2riyadh", 70, 116, "Multi0"),
            ("Shooter2", "r2hodeidah", 100, 106, "Multi1"), ("Tender", "r2jubail", 100, 116, "Multi0"),
            # Fleet support: identical half-health boats, one beside Al Jubail.
            ("Support", "r2jubail", 40, 124, "Multi0"), ("Supplied", "r2sadiq", 42, 126, "Multi0"),
            ("Unsupplied", "r2sadiq", 118, 126, "Multi0"),
            # Falcon One: one-pass precision strike and C4.
            ("Falcon", "r2falcon", 28, 36, "Multi0"), ("StrikeTarget", "htnk", 50, 40, "Multi1"),
            ("DemoTarget", "napowr", 30, 40, "Multi1"),
            # Frigate ASW against a submerged submarine.
            ("Hunter", "r2riyadh", 52, 104, "Multi0"), ("Sub", "sub", 53, 108, "Multi1"),
            # Secondary air-defense armaments: F-15SA AAM and frigate CIWS.
            ("Eagle", "r2f15sa", 110, 40, "Multi0"), ("EagleTarget", "jumpjet", 112, 44, "Multi1"),
            ("Ciws", "r2riyadh", 84, 104, "Multi0"), ("CiwsTarget", "jumpjet", 84, 99, "Multi1")]
        targets.update(lased=cell(22, 77), unlased=cell(62, 77), braced=cell(92, 76), loose=cell(112, 76),
                       strike=cell(50, 40), demolition=cell(30, 40), sub=cell(53, 108),
                       f15_aam=cell(112, 44), frigate_ciws=cell(84, 99))
        holds = ("Jtac", "Lased", "Unlased", "LasedTarget", "UnlasedTarget", "Braced", "Loose", "BracedTarget",
                 "LooseTarget", "Frigate", "Tender", "Shooter1", "Shooter2", "StrikeTarget", "Falcon", "Hunter",
                 "Sub", "Support", "Supplied", "Unsupplied", "Eagle", "EagleTarget", "Ciws", "CiwsTarget")
        lua += ["Supplied.Health = Supplied.MaxHealth / 2", "Unsupplied.Health = Unsupplied.MaxHealth / 2"]
        deploys.append((45, "r2sang", cell(90, 72)))
        attacks += (" Jtac.Attack(LasedTarget)"
                    " Trigger.AfterDelay(120, function() Lased.Attack(LasedTarget) Unlased.Attack(UnlasedTarget)"
                    " Braced.Attack(BracedTarget) Loose.Attack(LooseTarget) end)"
                    " Shooter1.Attack(Frigate) Shooter2.Attack(Tender)"
                    " Falcon.TargetAirstrike(StrikeTarget.CenterPosition) Falcon.Demolish(DemoTarget)"
                    " Eagle.Attack(EagleTarget) Ciws.Attack(CiwsTarget)"
                    " Trigger.AfterDelay(160, function() Hunter.Attack(Sub) end)")
    else:
        pairs = [
            # Drone guidance: identical RPG Hunters; one beside a Drone Spotter.
            ("Spotter", "r2yspot", 18, 72, "Multi0"), ("Guided", "r2yrpg", 20, 72, "Multi0"),
            ("GuidedTarget", "mtnk", 21, 75, "Multi1"), ("Unguided", "r2yrpg", 60, 72, "Multi0"),
            ("UnguidedTarget", "mtnk", 61, 75, "Multi1"),
            # Surveillance link: identical missile craft; one beside a Mokha.
            ("Mokha", "r2mokha", 68, 107, "Multi0"), ("Linked", "r2hodeidah", 70, 106, "Multi0"),
            ("LinkedTarget", "lcrf", 71, 114, "Multi1"), ("Alone", "r2hodeidah", 100, 106, "Multi0"),
            ("AloneTarget", "lcrf", 101, 114, "Multi1"),
            # Remote boat 11 cells from a Mokha: frozen until its radar deploys.
            ("Drifter", "r2sahaab", 40, 124, "Multi0"), ("Relay", "r2mokha", 40, 140, "Multi0"),
            ("BoatTarget", "lcrf", 40, 127, "Multi1"),
            # Camouflage: stationary Mountain Rifleman vs uncamouflaged RPG Hunter,
            # hunted by identical riflemen once both would have concealed.
            ("Hidden", "r2ymr", 90, 60, "Multi0"), ("Exposed", "r2yrpg", 110, 60, "Multi0"),
            ("Seeker1", "e1", 90, 56, "Multi1"), ("Seeker2", "e1", 110, 56, "Multi1")]
        targets.update(guided=cell(21, 75), unguided=cell(61, 75), linked=cell(71, 114), alone=cell(101, 114),
                       boat_target=cell(40, 127))
        holds = ("Spotter", "Guided", "Unguided", "GuidedTarget", "UnguidedTarget", "Mokha", "Linked", "Alone",
                 "LinkedTarget", "AloneTarget", "Relay", "Hidden", "Exposed", "Seeker1", "Seeker2", "BoatTarget")
        deploys.append((320, "r2mokha", cell(40, 140)))
        attacks += (" Guided.Attack(GuidedTarget) Unguided.Attack(UnguidedTarget)"
                    " Linked.Attack(LinkedTarget) Alone.Attack(AloneTarget) Drifter.Attack(BoatTarget)"
                    ' Trigger.AfterDelay(160, function() Seeker1.Stance = "AttackAnything"'
                    ' Seeker2.Stance = "AttackAnything" end)'
                    # Re-issue the boat's strike once the radar link can reach it.
                    " Trigger.AfterDelay(330, function() if not Drifter.IsDead then Drifter.Attack(BoatTarget) end end)")
    for name, kind, u, v, owner in pairs:
        actors += actor(name, kind, u, v, owner)
    lua += [f'{name}.Stance = "HoldFire"' for name in holds]
    lua.append(f"Trigger.AfterDelay(40, function() {attacks} end)")
    targets["_deploys"] = deploys
    return actors, lua, targets


def visual_scene(country, scene, facing):
    spec = FACTIONS[country]
    actors = ""
    face = f"\t\tFacing: {facing}\n"
    if scene == "infantry":
        reference = "e2" if spec["soviet"] else "e1"
        for i, kind in enumerate((reference,) + tuple(a for a in spec["units"] if a in art.SAUDI_INFANTRY + art.YEMEN_INFANTRY)):
            actors += actor("Review" + str(i), kind, 32 + i * 2, 64, extra=face)
        for i, kind in enumerate(spec["defenses"]):
            actors += actor("Defense" + str(i), kind, 33 + i * 3, 72)
        return actors, "Review2"
    if scene == "armor":
        reference = "htnk" if spec["soviet"] else "mtnk"
        ground = (reference,) + tuple(a for a in spec["units"] if a not in spec["ships"] and a not in
                                      art.SAUDI_INFANTRY + art.YEMEN_INFANTRY + ("r2f15sa", "r2ah64sa", "r2samad"))
        for i, kind in enumerate(ground):
            actors += actor("Review" + str(i), kind, 27 + (i % 3) * 3, 56 + (i // 3) * 6, extra=face)
        # Aircraft sit a row lower: their altitude projects them up the screen.
        for i, kind in enumerate(a for a in spec["units"] if a in ("r2f15sa", "r2ah64sa", "r2samad")):
            actors += actor("Air" + str(i), kind, 28 + i * 4, 74, extra=face)
        return actors, "Review4"
    lineup = ("dest" if not spec["soviet"] else "sapc",) + spec["ships"]
    for i, kind in enumerate(lineup):
        actors += actor("Review" + str(i), kind, 26 + i * 4, 112, extra=face)
    return actors, "Review2"


def run(resources, binaries, content, output, country, mode, scene="infantry", facing=640, color="E04444", terrain="temperate"):
    output.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix=country + "-" + mode + "-", dir=output))
    (profile / "Content").symlink_to(content, target_is_directory=True)
    targets = fixture(resources, profile, country, mode, scene, facing, color, terrain)
    spec = FACTIONS[country]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "OPENRA_AI_COMPANION": "1", "OPENRA_AI_COMPANION_READY": "1", "OPENRA_AI_STARTUP_ENABLED": "1",
           "OPENRA_AI_STARTUP_AUTO_ACT": "0", "OPENRA_AI_STARTUP_MUTED": "1", "OPENRA_AI_GRPC_PORT": str(port)}
    cmd = ["dotnet", str(binaries / "OpenRA.dll"), f"Engine.EngineDir={resources}", f"Engine.SupportDir={profile}",
           "Game.Mod=ra2", "Game.FetchNews=false", "Launch.Map=modern-art-review"]
    cmd += ["Graphics.Mode=Windowed", "Graphics.WindowedSize=1440,900", "Graphics.ViewportDistance=Close"] \
        if mode == "visual" else ["Game.Platform=Null"]
    if mode in ("combat", "edges"):
        cmd.append("Launch.Bots=Multi1:range-target")
    report = {"faction": country, "mode": mode, "passed": False, "profile": str(profile), "checks": {},
              "fast_build": True, "test_cash": 50000, "all_tech_cheat": False}
    if mode == "edges":
        report["edge_distances"] = targets.pop("_edges")
        targets["_deploys"] = []
    if mode == "visual":
        report.update(scene=scene, facing=facing, color=color, terrain=terrain)
    deadline_seconds = {"production": 200, "combat": 190, "edges": 150, "visual": 90}[mode]
    with (profile / "game.log").open("w") as log:
        process = subprocess.Popen(cmd, cwd=binaries, env=env, stdout=log, stderr=subprocess.STDOUT)
        bridge = OpenRABridge(f"127.0.0.1:{port}", timeout=1)
        try:
            deadline = time.monotonic() + deadline_seconds
            phase, placed, sent, cleared, moved, known, seen, history = "queue", set(), set(), set(), set(), {}, {}, {}
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    state = bridge.observe()
                    units = {u.kind: u for u in state.units}
                    buildings = {b.kind: b for b in state.buildings}
                    report["tick"] = state.tick
                    if state.done:
                        raise ValueError("Fixture ended unexpectedly")
                    if mode == "visual":
                        if state.tick >= 60:
                            frame = bridge.capture_frame()
                            if frame.scope != "rendered-player-viewport-fog-respecting":
                                raise ValueError("Expected actual rendered game pixels")
                            name = f"native-{country}-{scene}-{terrain}-{facing}-{color}.png"
                            (output / name).write_bytes(frame.png)
                            report.update(passed=True, scope=frame.scope, capture=name,
                                          units=sorted(units), buildings=sorted(buildings))
                            break
                    elif mode == "production":
                        phase = production_step(bridge, state, units, buildings, spec, report, phase, placed, sent, cleared, moved)
                        if phase == "done":
                            report["passed"] = True
                            break
                    else:
                        for deploy in list(targets.get("_deploys", ())):
                            when, kind, position = deploy
                            subject = near(state.units, kind, position)
                            if state.tick >= when and subject is not None:
                                receipt = bridge.execute_actions("red-sea-deploy-" + kind, state.tick,
                                                                 (ActionCommand("deploy", actor_id=subject.actor_id),))
                                report.setdefault("deploys", []).append(
                                    {"kind": kind, "tick": state.tick, "accepted": receipt.accepted})
                                targets["_deploys"].remove(deploy)
                        if combat_step(state, targets, report, known, seen, mode, country, history):
                            report["passed"] = True
                            break
                    report["phase"] = phase
                    bridge.update_companion_status("ready", "Private Red Sea verification", muted=True)
                except RuntimeError as exc:
                    report["last_connection_error"] = str(exc)
                time.sleep(.15)
            if not report["passed"]:
                report.setdefault("error", "Process ended or deadline reached in " + phase)
        except Exception as exc:
            report["error"] = str(exc)
        finally:
            bridge.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    name = "result.json" if mode != "visual" else f"result-{scene}-{terrain}-{facing}-{color}.json"
    (output / name).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
    return report["passed"]


def production_step(bridge, state, units, buildings, spec, report, phase, placed, sent, cleared, moved):
    everything = spec["units"] + spec["defenses"]
    if phase == "queue":
        available = set(state.available_production)
        missing = set(everything) - available
        if missing:
            raise ValueError("Missing production: " + str(sorted(missing)))
        forbidden = spec["forbidden"] & available
        if forbidden:
            raise ValueError("Foreign or replaced choices offered: " + str(sorted(forbidden)))
        report["available"] = sorted(available)
        commands = [ActionCommand("train", item_type=a) for a in spec["units"]]
        commands += [ActionCommand("build", item_type=a) for a in spec["defenses"]]
        if spec["cargo"][1] == "htk":
            commands.append(ActionCommand("train", item_type="htk"))
        for start in range(0, len(commands), 12):
            receipt = bridge.execute_actions("production-" + str(start), state.tick, tuple(commands[start:start + 12]))
            if not receipt.accepted:
                raise ValueError(str(receipt.as_dict()))
        return "produce"
    for a in spec["defenses"]:
        if a in buildings:
            placed.add(a)
        elif a not in sent and bridge.execute_actions("place-" + a + "-" + str(state.tick), state.tick,
                                                      (ActionCommand("place_building", item_type=a),)).accepted:
            sent.add(a)
    for i, a in enumerate(spec["vehicles"] + ("htk",)):
        if a in units and a not in cleared and bridge.execute_actions(
                "clear-" + a, state.tick, (ActionCommand("move", actor_id=units[a].actor_id, target_x=20 + i * 4, target_y=65),)).accepted:
            cleared.add(a)
    passenger, carrier = spec["cargo"]
    if phase == "produce" and set(spec["units"]) <= units.keys() and carrier in units and len(placed) == 3:
        report["produced"] = {a: {"name": state.actor_name(a), "weapon": units[a].weapon, "air": units[a].can_target_air,
                                  "ground": units[a].can_target_ground, "range": units[a].attack_range,
                                  "minimum_range": units[a].minimum_attack_range} for a in spec["units"]}
        report["defense_domains"] = {a: {"air": buildings[a].can_target_air, "ground": buildings[a].can_target_ground}
                                     for a in spec["defenses"]}
        for a in spec["air_only"]:
            if not units[a].can_target_air or units[a].can_target_ground:
                raise ValueError("Air defense must be air-only: " + a)
        for a in spec["both_domains"]:
            if not units[a].can_target_air or not units[a].can_target_ground:
                raise ValueError("Multirole bridge metadata is missing a domain: " + a)
        receipt = bridge.execute_actions("red-sea-load", state.tick, (ActionCommand(
            "enter_transport", actor_id=units[passenger].actor_id, target_actor_id=units[carrier].actor_id),))
        if not receipt.accepted:
            raise ValueError("Load rejected: " + json.dumps(receipt.as_dict()))
        return "load"
    if phase == "load" and units[carrier].passenger_count == 1:
        report["cargo_loaded"] = True
        bridge.execute_actions("red-sea-unload", state.tick, (ActionCommand("unload", actor_id=units[carrier].actor_id),))
        return "unload"
    if phase == "unload" and passenger in units and units[carrier].passenger_count <= 0:
        report["cargo_round_trip"] = True
        ships = spec["ships"]
        if "r2mokha" in units:
            # Active radar extends the Mokha's link so the remote boat can follow.
            bridge.execute_actions("red-sea-radar", state.tick, (ActionCommand("deploy", actor_id=units["r2mokha"].actor_id),))
        for i, a in enumerate(ships):
            bridge.execute_actions("water-" + a, state.tick, (ActionCommand(
                "move", actor_id=units[a].actor_id, target_x=25 + i * 5, target_y=115),))
        return "water"
    if phase == "water":
        for i, a in enumerate(spec["ships"]):
            if a in units and (units[a].cell_x, units[a].cell_y) == (25 + i * 5, 115):
                moved.add(a)
        report["water_movement"] = sorted(moved)
        if len(moved) == len(spec["ships"]):
            report["defenses"] = sorted(placed)
            return "done"
    return phase


def near(units, kind, position, radius=3):
    return next((u for u in units if u.kind == kind and abs(u.cell_x - position[0]) + abs(u.cell_y - position[1]) <= radius), None)


def damage_seen(state, targets, known, report, history):
    enemies = {u.actor_id: u for u in state.visible_enemies + state.visible_enemy_buildings}
    jumps = history.setdefault("_jumps", {})
    for name, pos in targets.items():
        if name.startswith("_") or pos is None:
            continue
        if name not in known:
            unit = next((u for u in enemies.values() if (u.cell_x, u.cell_y) == pos), None)
            if unit is None:
                unit = next((u for u in enemies.values() if u.kind in ("gapowr", "napowr") and
                             abs(u.cell_x - pos[0]) + abs(u.cell_y - pos[1]) <= 3), None)
            if unit:
                known[name] = unit.actor_id
            continue
        unit = enemies.get(known[name])
        if unit is None:
            # A known target that vanished was destroyed (C4 demolition).
            report["checks"][name] = 1.0
            continue
        damage = round(1 - unit.hp_percent, 4)
        if damage > 0:
            report["checks"][name] = damage
        jumps[name] = max(jumps.get(name, 0), damage - history.get(name, 0))
        history[name] = damage


def combat_step(state, targets, report, known, seen, mode, country, history):
    damage_seen(state, targets, known, report, history)
    checks = report["checks"]
    wanted = [name for name in targets if not name.startswith("_") and targets[name] is not None]
    report["missing_damage"] = sorted(name for name in wanted if name not in checks)
    if mode == "edges":
        return not report["missing_damage"]
    own = state.units
    abilities = report.setdefault("abilities", {})
    if country == "saudi":
        abilities["laser_guidance"] = checks.get("lased", 0) > checks.get("unlased", 0) * 1.05 > 0
        abilities["brace"] = checks.get("braced", 0) > checks.get("loose", 0) * 1.05 > 0
        frigate, tender = near(own, "r2riyadh", cell(70, 116), 5), near(own, "r2jubail", cell(100, 116), 5)
        if frigate and tender:
            seen["frigate_hp_lost"] = round((1 - frigate.hp_percent) * 700, 1)
            seen["tender_hp_lost"] = round((1 - tender.hp_percent) * 800, 1)
        abilities["interceptors"] = seen.get("tender_hp_lost", 0) >= 60 and \
            seen.get("frigate_hp_lost", 0) < seen.get("tender_hp_lost", 0) * .75
        supplied, unsupplied = near(own, "r2sadiq", cell(42, 126)), near(own, "r2sadiq", cell(118, 126))
        if supplied and unsupplied:
            seen["supplied_hp"], seen["unsupplied_hp"] = supplied.hp_percent, unsupplied.hp_percent
        abilities["fleet_support"] = seen.get("supplied_hp", 0) >= .75 and seen.get("unsupplied_hp", 1) <= .55
        abilities["precision_strike"] = checks.get("strike", 0) > 0
        abilities["c4_demolition"] = checks.get("demolition", 0) >= 1.0
        abilities["asw"] = checks.get("sub", 0) > 0
    else:
        abilities["drone_guidance"] = checks.get("guided", 0) > checks.get("unguided", 0) * 1.05 > 0
        abilities["surveillance_link"] = checks.get("linked", 0) > checks.get("alone", 0) * 1.05 > 0
        drifter = near(own, "r2sahaab", cell(40, 124), 40)
        if drifter and state.tick < 320:
            seen.setdefault("usv_start", [drifter.cell_x, drifter.cell_y])
            seen["usv_before_radar"] = [drifter.cell_x, drifter.cell_y]
        if seen.get("usv_start") and state.tick >= 320 and drifter is None:
            seen.setdefault("usv_gone_tick", state.tick)
        abilities["usv_link_gate"] = bool(seen.get("usv_start")) and seen.get("usv_before_radar") == seen.get("usv_start")
        abilities["usv_expended"] = checks.get("boat_target", 0) > 0 and "usv_gone_tick" in seen
        hidden, exposed = near(own, "r2ymr", cell(90, 60)), near(own, "r2yrpg", cell(110, 60))
        if hidden and exposed:
            seen["hidden_hp"], seen["exposed_hp"] = hidden.hp_percent, exposed.hp_percent
        abilities["camouflage"] = seen.get("exposed_hp", 1) < .95 and seen.get("hidden_hp", 0) >= .999
        # The delayed charge lands as one large step; carbine hits are tiny.
        seen["largest_structure_step"] = history.get("_jumps", {}).get("r2wadighost", 0)
        abilities["remote_charge"] = seen["largest_structure_step"] >= .025
        abilities["samad_expended"] = checks.get("r2samad", 0) > 0 and not any(u.kind == "r2samad" for u in own)
    report["ability_evidence"] = dict(seen)
    return state.tick >= 1200 and not report["missing_damage"] and all(abilities.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("resources", "binaries", "content", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--faction", choices=tuple(FACTIONS), required=True)
    parser.add_argument("--mode", choices=("production", "combat", "edges", "visual"), default="production")
    parser.add_argument("--scene", choices=("infantry", "armor", "navy"), default="infantry")
    parser.add_argument("--facing", type=int, default=640)
    parser.add_argument("--color", default="E04444")
    parser.add_argument("--terrain", choices=("temperate", "snow"), default="temperate")
    args = parser.parse_args()
    if not re.fullmatch("[0-9A-Fa-f]{6}", args.color) or not 0 <= args.facing < 1024:
        parser.error("Expected an RGB hex color and a facing in 0..1023")
    raise SystemExit(0 if run(*(getattr(args, k).resolve() for k in ("resources", "binaries", "content", "output")),
                              args.faction, args.mode, args.scene, args.facing, args.color, args.terrain) else 1)
