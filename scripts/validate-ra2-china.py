#!/usr/bin/env python3
"""Isolated China production, transport and water-pathing acceptance test.

Private prebuilt economy, 50k test credits and fast production; normal faction
and technology gates remain active. Never connects to the user's bridge/port.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import tempfile
import time

from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.models import ActionCommand
from ra2_china_assets import CHINA_UNITS, DEFENSES

SPEC = importlib.util.spec_from_file_location("review", Path(__file__).with_name("validate-ra2-faction-art.py"))
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


def fixture(resources, profile, *, visual=False, scene="infantry"):
    target = ART.fixture(resources, profile)
    text = (target/"map.yaml").read_text()
    text = text.split("Actors:\n")[0].replace("Faction: china", "Faction: china")
    actors = [("ReviewBase", "gacnst", 74, 10), ("EnemyBase", "nacnst", 115, -40),
              ("Spawn0", "mpspawn", 74, 10), ("Spawn1", "mpspawn", 115, -40)]
    buildings = ("gaweap", "gapowr", "gapowr", "garefn", "gaairc", "gapile", "gatech", "gapowr")
    actors += [("Factory"+str(i), a, 42+i*8, -10 if not visual else -30) for i,a in enumerate(buildings)]
    actors += [("Yard", "gayard", 75, 30)]
    if visual and scene=="modes":
        for i,a in enumerate(("r2cnportable", "r2cnportable", "r2cnnetwork")):
            actors += [("Review"+str(i),a,60+4*i,-2-4*i)]
    elif visual and scene=="infantry":
        # Native, GPU-rendered infantry/defense comparison beside a stock GI.
        for i,a in enumerate(("e1", "r2cnrifle", "r2cnportable", "r2cnnetwork", "r2redspear")):
            actors += [("Review"+str(i),a,61+2*i,-3-2*i)]
        for i,a in enumerate(DEFENSES): actors += [("Defense"+str(i),a,64+4*i,3-4*i)]
    elif visual:
        lineup=("r2qilin","r2zbd","r2phl","r2lynx","r2crane","r2skyspear") if scene=="armor" else ("r2haiying","r2luyang","r2haiwang","r2kunlun","r2jiaolong")
        for i,a in enumerate(lineup):
            u,v=(30+(i%3)*3,60+(i//3)*8) if scene=="armor" else (30+(i%3)*3,108+(i//3)*8)
            actors += [("Review"+str(i),a,u+v//2,v//2-u)]
    text += "Actors:\n"
    for name,a,x,y in actors:
        owner = "Neutral" if a=="mpspawn" else "Multi1" if name=="EnemyBase" else "Multi0"
        text += f"\t{name}: {a}\n\t\tOwner: {owner}\n\t\tLocation: {x},{y}\n"
        if name.startswith("Review") and a != "gacnst": text += "\t\tFacing: 640\n"
        if visual and scene=="modes" and name in ("Review1","Review2"):
            text += "\t\tDeployState: Deployed\n"
    text += "Rules:\n\tWorld:\n\t\t-SpawnStartingUnits:\n\t\tLuaScript:\n\t\t\tScripts: review.lua\n\tPlayer:\n\t\tDeveloperMode:\n\t\t\tCheckboxEnabled: true\n\t\t\tFastBuild: true\n\t\tShroud:\n\t\t\tFogEnabled: false\n\t\t\tExploredMapEnabled: true\n"
    if visual and scene=="armor":
        # Static art review only: keep the parked jet in its lineup instead of
        # returning to the distant factory. Combat tests retain normal behavior.
        text += "\tr2skyspear:\n\t\tAircraft:\n\t\t\tIdleBehavior: None\n\t\t\tSpeed: 0\n\t\t\tCruiseAltitude: 0\n"
    if visual and scene=="modes":
        # Review the real conditional decorations together without changing the
        # user's selection. Production rules still require selection to show them.
        text += "\tr2cnportable:\n\t\tWithTextDecoration@AT:\n\t\t\tRequiresSelection: false\n\t\tWithTextDecoration@AA:\n\t\t\tRequiresSelection: false\n\tr2cnnetwork:\n\t\tWithTextDecoration@RELAY:\n\t\t\tRequiresSelection: false\n"
    (target/"map.yaml").write_text(text)
    focus = ("Review2" if scene=="infantry" else "Review1") if visual else "ReviewBase"
    (target/"review.lua").write_text(f'WorldLoaded = function() Player.GetPlayer("Multi0").Cash = 50000 Camera.Position = {focus}.CenterPosition end\n')
    data = bytearray((target/"map.bin").read_bytes())
    version,w,h,tiles,heights,resources_offset = struct.unpack_from("<BHHIII",data)
    assert version==2
    # A real water basin; test amphibious and naval movement, not a locomotor cheat.
    for u in range(w):
        for v in range(100,h): struct.pack_into("<HB",data,tiles+3*(u*h+v),314,(u%2)+2*(v%2))
    (target/"map.bin").write_bytes(data)
    return target


def run(resources,binaries,content,output,visual=False,scene="infantry"):
    output.mkdir(parents=True,exist_ok=True)
    profile=Path(tempfile.mkdtemp(prefix="china-",dir=output))
    (profile/"Content").symlink_to(content,target_is_directory=True)
    fixture(resources,profile,visual=visual,scene=scene)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    env={**os.environ,"OPENRA_AI_COMPANION":"1","OPENRA_AI_COMPANION_READY":"1",
         "OPENRA_AI_STARTUP_ENABLED":"1","OPENRA_AI_STARTUP_AUTO_ACT":"0",
         "OPENRA_AI_STARTUP_MUTED":"1","OPENRA_AI_GRPC_PORT":str(port)}
    cmd=["dotnet",str(binaries/"OpenRA.dll"),f"Engine.EngineDir={resources}",f"Engine.SupportDir={profile}",
         "Game.Mod=ra2","Game.FetchNews=false","Launch.Map=modern-art-review"]
    cmd += ["Graphics.Mode=Windowed","Graphics.WindowedSize=1440,900","Graphics.ViewportDistance=Close"] if visual else ["Game.Platform=Null"]
    report={"passed":False,"profile":str(profile),"fast_build":True,"test_cash":50000,"all_tech":False}
    with (profile/"game.log").open("w") as log:
        process=subprocess.Popen(cmd,cwd=binaries,env=env,stdout=log,stderr=subprocess.STDOUT)
        bridge=OpenRABridge(f"127.0.0.1:{port}",timeout=1)
        try:
            deadline=time.monotonic()+140
            phase="queue"; placed=set(); sent=set(); naval_moved=set(); cargo_loaded=False; cleared=set()
            carriers=("r2zbd","r2crane","r2kunlun"); carrier_index=0; cargo_checks=[]
            stage_tick=0; stage_destination=None
            while process.poll() is None and time.monotonic()<deadline:
                try:
                    state=bridge.observe()
                    units={u.kind:u for u in state.units}
                    structures={b.kind:b for b in state.buildings}
                    report["last_state"]={"tick":state.tick,"units":sorted(units),"buildings":sorted(structures),"production":state.production,"cash":state.cash}
                    if state.done: raise ValueError("Fixture ended unexpectedly")
                    if visual and state.tick>=40:
                        frame=bridge.capture_frame()
                        assert frame.scope=="rendered-player-viewport-fog-respecting"
                        (output/"native-china-review.png").write_bytes(frame.png)
                        report.update(passed=True,scope=frame.scope,tick=state.tick)
                        break
                    if visual:
                        time.sleep(.15)
                        continue
                    if phase=="queue":
                        available=set(state.available_production)
                        missing=set(CHINA_UNITS+DEFENSES)-available
                        if missing: raise ValueError("Missing gated production: "+str(missing))
                        foreign={"r2bozkir","r2karrar","e1","mtnk","fv","gapill","nasam","atesla","lcrf"}&available
                        if foreign: raise ValueError("China still offers replaced combat units: "+str(foreign))
                        report["available"]=sorted(available)
                        commands=[ActionCommand("train",item_type=a) for a in CHINA_UNITS]
                        commands += [ActionCommand("build",item_type=a) for a in DEFENSES]
                        for start in range(0,len(commands),12):
                            receipt=bridge.execute_actions("china-production-"+str(start),state.tick,tuple(commands[start:start+12]))
                            if not receipt.accepted: raise ValueError(str(receipt.as_dict()))
                        phase="produce"
                    for a in DEFENSES:
                        if a in structures: placed.add(a)
                        elif a not in sent:
                            receipt=bridge.execute_actions("place-"+a+"-"+str(state.tick),state.tick,
                                (ActionCommand("place_building",item_type=a),))
                            if receipt.accepted: sent.add(a)
                    # Empty the factory apron as each ground vehicle finishes;
                    # an idle ring of 8 test units otherwise traps the final APC.
                    if phase=="produce":
                        for i,a in enumerate(("r2qilin","r2zbd","r2phl","r2mantis","r2lynx")):
                            if a in units and a not in cleared:
                                receipt=bridge.execute_actions("clear-"+a,state.tick,(ActionCommand("move",actor_id=units[a].actor_id,target_x=20+i*4,target_y=65),))
                                if receipt.accepted: cleared.add(a)
                    if set(CHINA_UNITS)<=units.keys() and len(placed)==3 and phase=="produce":
                        report["produced"]={a:{"name":state.actor_name(a),"weapon":units[a].weapon,
                            "air":units[a].can_target_air,"ground":units[a].can_target_ground} for a in CHINA_UNITS}
                        for a in ("r2mantis","r2skyspear"):
                            if not units[a].can_target_air or units[a].can_target_ground: raise ValueError("Incorrect anti-air targeting: "+a)
                        commands=(ActionCommand("enter_transport",actor_id=units["r2cnrifle"].actor_id,target_actor_id=units[carriers[carrier_index]].actor_id),)
                        if not bridge.execute_actions("china-load",state.tick,commands).accepted: raise ValueError("Load rejected")
                        phase="load"
                    if phase=="load" and units[carriers[carrier_index]].passenger_count==1:
                        cargo_loaded=True
                        bridge.execute_actions("china-unload-"+str(carrier_index),state.tick,(ActionCommand("unload",actor_id=units[carriers[carrier_index]].actor_id),))
                        phase="unload"
                    if phase=="unload" and "r2cnrifle" in units and units[carriers[carrier_index]].passenger_count<=0:
                        cargo_checks.append(carriers[carrier_index])
                        if carrier_index+1<len(carriers):
                            carrier_index+=1
                            # Stage the next carrier beside the unloaded rifleman.
                            carrier=units[carriers[carrier_index]]
                            rifle=units["r2cnrifle"]
                            stage_tick=state.tick
                            stage_destination=(rifle.cell_x+2,rifle.cell_y+2)
                            bridge.execute_actions("stage-carrier-"+str(carrier_index),state.tick,
                                (ActionCommand("move",actor_id=carrier.actor_id,target_x=rifle.cell_x+2,target_y=rifle.cell_y+2),))
                            phase="stage-carrier"
                            continue
                        report["cargo_round_trip"]=cargo_loaded
                        report["cargo_carriers"]=cargo_checks
                        # Distinct clear water cells for all ships and the amphibian.
                        for i,a in enumerate(("r2zbd","r2haiying","r2luyang","r2haiwang","r2kunlun","r2jiaolong")):
                            dest=(25+i*5,115)
                            bridge.execute_actions("water-"+a,state.tick,(ActionCommand("move",actor_id=units[a].actor_id,target_x=dest[0],target_y=dest[1]),))
                        phase="water"
                    if (phase=="stage-carrier" and state.tick>=stage_tick+20 and units[carriers[carrier_index]].idle
                            and (units[carriers[carrier_index]].cell_x,units[carriers[carrier_index]].cell_y)==stage_destination):
                        receipt=bridge.execute_actions("load-carrier-"+str(carrier_index),state.tick,
                            (ActionCommand("enter_transport",actor_id=units["r2cnrifle"].actor_id,target_actor_id=units[carriers[carrier_index]].actor_id),))
                        if receipt.accepted: phase="load"
                    if phase=="water":
                        for i,a in enumerate(("r2zbd","r2haiying","r2luyang","r2haiwang","r2kunlun","r2jiaolong")):
                            if (units[a].cell_x,units[a].cell_y)==(25+i*5,115): naval_moved.add(a)
                        if len(naval_moved)==6:
                            report.update(passed=True,tick=state.tick,defenses=sorted(placed),water_movement=sorted(naval_moved))
                            break
                    report["phase"]=phase
                    report["cargo_checks"]=cargo_checks
                    report["carrier_under_test"]=carriers[carrier_index]
                    bridge.update_companion_status("ready","Isolated China verification",muted=True)
                except RuntimeError as exc: report["last_connection_error"]=str(exc)
                time.sleep(.15)
            if not report["passed"]: report["error"]="Timed out or process exited in "+phase
        except Exception as exc: report["error"]=str(exc)
        finally:
            bridge.close()
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    (output/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report),flush=True)
    return report["passed"]


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("resources","binaries","content","output"): parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--visual",action="store_true")
    parser.add_argument("--visual-scene",choices=("infantry","armor","navy","modes"),default="infantry")
    args=parser.parse_args()
    raise SystemExit(0 if run(*(getattr(args,k).resolve() for k in ("resources","binaries","content","output")),args.visual,args.visual_scene) else 1)
