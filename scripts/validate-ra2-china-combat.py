#!/usr/bin/env python3
"""Bounded native combat checks on a disposable China range, never a live match."""
import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time

from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.models import ActionCommand

SPEC=importlib.util.spec_from_file_location("china_test",Path(__file__).with_name("validate-ra2-china.py"))
BASE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(BASE)
PAIRS=(
    ("r2cnrifle","e1"),("r2cnportable","mtnk"),("r2redspear","e1"),
    ("r2qilin","mtnk"),("r2lynx","e1"),("r2phl","mtnk"),
    ("r2mantis","jumpjet"),("r2zbd","e1"),("r2cnnetwork","e1"),
    ("r2cloud","mtnk"),("r2crane","e1"),("r2skyspear","jumpjet"),
    ("r2bastion","e1"),("r2skyshield","jumpjet"),
    ("r2luyang","sub"),("r2haiying","lcrf"),("r2haiwang","lcrf"),("r2jiaolong","lcrf"))



def run(resources,binaries,content,output):
    output.mkdir(parents=True,exist_ok=True)
    profile=Path(tempfile.mkdtemp(prefix="combat-",dir=output))
    (profile/"Content").symlink_to(content,target_is_directory=True)
    target=BASE.fixture(resources,profile)
    text=(target/"map.yaml").read_text()
    actors=""; targets={}; own_ids={}; lua=[]
    def actor(name,kind,u,v,owner):
        x,y=u+(v+1)//2,v//2-u
        return f"\t{name}: {kind}\n\t\tOwner: {owner}\n\t\tLocation: {x},{y}\n"
    for i,(kind,victim) in enumerate(PAIRS):
        u=8+(i%6)*20; v=14+(i//6)*25
        if i>=14: u=20+(i-14)*25; v=108
        if kind=="r2skyspear": u,v=48,47  # Near the actual airfield for a bounded rearm cycle.
        # Howitzers need their native minimum distance. These are map-grid
        # coordinates, not world-distance cells on RA2's isometric grid.
        du,dv=(3,6) if kind=="r2phl" else (2,4)
        actors+=actor("A"+str(i),kind,u,v,"Multi0")+actor("T"+str(i),victim,u+du,v+dv,"Multi1")
        targets[kind]=(u+du,v+dv)
        own_ids[kind]=(u,v)
        lua += [f'A{i}.Stance = "HoldFire"',f'T{i}.Stance = "HoldFire"']
        if kind == "r2skyspear":
            # The jet initially returns to its real airfield. A stationary spotter
            # preserves sight of its target while it makes its attack approach.
            actors += actor("AirSpotter", "r2cnrifle", u+du+1, v+dv, "Multi0")
            lua += ['AirSpotter.Stance = "HoldFire"']
    # Two identical riflemen; only the first receives a deployed network relay. Compare
    # damage after synchronized firing, rather than inferring from rule text.
    actors+=actor("Marker","r2cnnetwork",64,80,"Multi0")
    actors+=actor("MarkedRifle","r2cnrifle",67,80,"Multi0")+actor("MarkedTarget","e1",69,84,"Multi1")
    actors+=actor("ControlRifle","r2cnrifle",97,80,"Multi0")+actor("ControlTarget","e1",99,84,"Multi1")
    for name in ("Marker","MarkedRifle","MarkedTarget","ControlRifle","ControlTarget"): lua += [name+'.Stance = "HoldFire"']
    actors+=actor("ModeTeam","r2cnportable",10,80,"Multi0")
    actors+=actor("ModeAir","jumpjet",12,84,"Multi1")+actor("ModeTank","mtnk",13,83,"Multi1")
    for name in ("ModeTeam","ModeAir","ModeTank"): lua += [name+'.Stance = "HoldFire"']
    edge_targets={}; edge_origins={}
    for label,kind,victim,u,v,du,dv in (
            ("artillery","r2phl","mtnk",16,46,0,16),
            ("coastal","r2haiying","lcrf",95,115,6,0),
            ("skyshield","r2skyshield","jumpjet",75,15,0,15),
            ("mantis","r2mantis","jumpjet",115,40,0,13),
            ("naval-aa","r2haiying","jumpjet",85,110,0,12)):
        # Lua global names cannot contain hyphens.
        label=label.replace("-","")
        actors+=actor("Edge"+label,kind,u,v,"Multi0")
        actors+=actor("Target"+label,victim,u+du,v+dv,"Multi1")
        actors+=actor("Spotter"+label,"r2cloud",u+du,v+dv+1,"Multi0")
        edge_targets[label]=(u+du,v+dv)
        edge_origins[label]=(kind,u,v)
        lua += [f'Edge{label}.Stance = "HoldFire"',f'Target{label}.Stance = "HoldFire"',f'Spotter{label}.Stance = "HoldFire"']
    text=text.replace("Rules:\n",actors+"Rules:\n")
    # Create the enemy player with an inert bot type. Existing bot modules only
    # activate for normal/medium/rush/turtle/naval, so no AI overrides HoldFire.
    text=text.replace("\tPlayer:\n", "\tPlayer:\n\t\tModularBot@range:\n\t\t\tName: ra2-bot-normal\n\t\t\tType: range-target\n")
    for victim in {v for _,v in PAIRS}:
        text+=f"\t{victim}:\n\t\tHealth:\n\t\t\tHP: 10000\n"
        if victim == "e1": text += "\t\t-TakeCover:\n"
    (target/"map.yaml").write_text(text)
    start=[f"A{i}.Attack(T{i})" for i in range(len(PAIRS))]
    # AttackFollow normally advances toward a preferred firing distance. Pin
    # movement for this range contract without changing weapon or actor stats.
    for label in edge_targets:
        # Ask the engine for actual world positions. A map-grid delta of (4,4)
        # is not four or sqrt(32) range cells in RA2's staggered isometric grid.
        start += [f'do local d = Target{label}.CenterPosition - Edge{label}.CenterPosition '
                  f'local c = Map.CenterOfCell(Target{label}.Location) - Map.CenterOfCell(Edge{label}.Location) '
                  f'print("CHINA_EDGE|{label}|" .. math.sqrt(d.X*d.X+d.Y*d.Y) .. "|" .. math.sqrt(c.X*c.X+c.Y*c.Y)) end',
                  f"Edge{label}.Attack(Target{label}, false)"]
    script="WorldLoaded = function()\n  "+"\n  ".join(lua)+"\n"
    script+="  Trigger.AfterDelay(40, function() "+" ".join(start)+" end)\n"
    script+="  Trigger.AfterDelay(80, function() MarkedRifle.Attack(MarkedTarget) ControlRifle.Attack(ControlTarget) end)\nend\n"
    (target/"review.lua").write_text(script)
    with socket.socket() as sock: sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    env={**os.environ,"OPENRA_AI_COMPANION":"1","OPENRA_AI_COMPANION_READY":"1","OPENRA_AI_STARTUP_ENABLED":"1",
         "OPENRA_AI_STARTUP_AUTO_ACT":"0","OPENRA_AI_STARTUP_MUTED":"1","OPENRA_AI_GRPC_PORT":str(port)}
    cmd=["dotnet",str(binaries/"OpenRA.dll"),f"Engine.EngineDir={resources}",f"Engine.SupportDir={profile}",
         "Game.Mod=ra2","Game.Platform=Null","Game.FetchNews=false","Launch.Map=modern-art-review","Launch.Bots=Multi1:range-target"]
    report={"passed":False,"profile":str(profile),"target_hp":10000,"checks":{}}
    with (profile/"game.log").open("w") as log:
        process=subprocess.Popen(cmd,cwd=binaries,env=env,stdout=log,stderr=subprocess.STDOUT)
        bridge=OpenRABridge(f"127.0.0.1:{port}",timeout=1)
        try:
            end=time.monotonic()+100
            known_targets={}; edge_actor_ids={}
            interceptor_ordered=False; network_deployed=False
            mode_phase="baseline"; mode_tick=0
            while process.poll() is None and time.monotonic()<end:
                try:
                    state=bridge.observe()
                    if not network_deployed and state.tick>=10:
                        network=next((u for u in state.units if u.kind=="r2cnnetwork" and (u.cell_x,u.cell_y)==(64,80)),None)
                        if network:
                            receipt=bridge.execute_actions("deploy-network",state.tick,(ActionCommand("deploy",actor_id=network.actor_id),))
                            network_deployed=receipt.accepted
                            report["network_deploy"]=receipt.as_dict()
                    enemy={u.actor_id:u for u in state.visible_enemies}
                    own={u.actor_id:u for u in state.units}
                    mode_team=next((u for u in own.values() if u.kind=="r2cnportable" and (u.cell_x,u.cell_y)==(10,80)),None)
                    mode_air=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==(12,84)),None)
                    mode_tank=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==(13,83)),None)
                    if mode_team and mode_air and mode_tank:
                        report["mode_team"]=asdict(mode_team)
                        report["mode_targets"]={"air":mode_air.hp_percent,"tank":mode_tank.hp_percent}
                        if mode_phase=="baseline" and state.tick>=20:
                            receipt=bridge.execute_actions("AT-cannot-air",state.tick,(ActionCommand("attack",actor_id=mode_team.actor_id,target_actor_id=mode_air.actor_id),))
                            report["at_air_order"]=receipt.as_dict()
                            mode_phase="deploy-aa"; mode_tick=state.tick
                        elif mode_phase=="deploy-aa" and state.tick>=mode_tick+80:
                            report["at_mode_did_not_hit_air"]=mode_air.hp_percent==1
                            receipt=bridge.execute_actions("portable-AA-mode",state.tick,(ActionCommand("deploy",actor_id=mode_team.actor_id),))
                            if receipt.accepted: mode_phase="attack-air"; mode_tick=state.tick
                        elif mode_phase=="attack-air" and state.tick>=mode_tick+20:
                            receipt=bridge.execute_actions("portable-air-target",state.tick,(ActionCommand("attack",actor_id=mode_team.actor_id,target_actor_id=mode_air.actor_id),))
                            if receipt.accepted: mode_phase="air-damage"
                        elif mode_phase=="air-damage" and mode_air.hp_percent<1:
                            report["portable_aa_hit"]=True
                            receipt=bridge.execute_actions("portable-back-to-AT",state.tick,(ActionCommand("deploy",actor_id=mode_team.actor_id),))
                            if receipt.accepted: mode_phase="attack-tank"; mode_tick=state.tick
                        elif mode_phase=="attack-tank" and state.tick>=mode_tick+30 and mode_team.can_target_ground:
                            receipt=bridge.execute_actions("portable-tank-target",state.tick,(ActionCommand("attack",actor_id=mode_team.actor_id,target_actor_id=mode_tank.actor_id),))
                            if receipt.accepted: mode_phase="tank-damage"
                        elif mode_phase=="tank-damage" and mode_tank.hp_percent<1:
                            report["portable_returned_to_at"]=True
                    report["mode_phase"]=mode_phase
                    for label,pos in edge_targets.items():
                        if label not in edge_actor_ids:
                            kind,u,v=edge_origins[label]
                            actor_unit=next((a for a in (*state.units,*state.buildings) if a.kind==kind and (a.cell_x,a.cell_y)==(u,v)),None)
                            if actor_unit: edge_actor_ids[label]=actor_unit.actor_id
                        target_unit=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==pos),None)
                        edge_actor=next((a for a in (*state.units,*state.buildings) if a.actor_id==edge_actor_ids.get(label)),None)
                        report.setdefault("edge_diagnostics",{})[label]={
                            "actor_id":edge_actor_ids.get(label),
                            "position":(edge_actor.cell_x,edge_actor.cell_y) if edge_actor else None,
                            "activity":edge_actor.current_activity if edge_actor else None,
                            "target_hp":target_unit.hp_percent if target_unit else None}
                        if target_unit and target_unit.hp_percent<1:
                            actor_unit=next((a for a in (*state.units,*state.buildings) if a.actor_id==edge_actor_ids.get(label)),None)
                            if actor_unit and (actor_unit.cell_x,actor_unit.cell_y)==edge_origins[label][1:]:
                                report.setdefault("range_edge",{})[label]={"passed":True,"target_hp_fraction":target_unit.hp_percent,
                                    "fired_without_moving":True,"declared_range_world_units":actor_unit.attack_range}
                    if any(u.kind=="r2haiwangdrone" for u in own.values()):
                        report["carrier_wing_spawned"]=True
                    report["diagnostics"]=[asdict(u) for u in own.values() if u.kind in ("r2skyspear","r2cnnetwork")]
                    report["tick"]=state.tick
                    for name,pos in targets.items():
                        if name not in known_targets:
                            target_unit=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==pos),None)
                            if target_unit: known_targets[name]=target_unit.actor_id
                        target_unit=enemy.get(known_targets.get(name))
                        if target_unit and target_unit.hp_percent<1:
                            report["checks"][name]={"passed":True,"target_hp_fraction":target_unit.hp_percent}
                    interceptor=next((u for u in own.values() if u.kind=="r2skyspear"),None)
                    air_target=enemy.get(known_targets.get("r2skyspear"))
                    if interceptor and interceptor.ammo<4:
                        report["interceptor_ammo_used"]=True
                    if interceptor and interceptor.ammo==4 and interceptor.idle and report.get("interceptor_ammo_used"):
                        report["interceptor_rearmed"]=True
                    if (interceptor and interceptor.idle and air_target and not interceptor_ordered
                            and "r2skyspear" not in report["checks"] and state.tick>100):
                        receipt=bridge.execute_actions("intercept-air-target",state.tick,
                            (ActionCommand("attack",actor_id=interceptor.actor_id,target_actor_id=air_target.actor_id),))
                        report["interceptor_order"]=receipt.as_dict()
                        interceptor_ordered=receipt.accepted
                    marked=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==(69,84)),None)
                    control=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==(99,84)),None)
                    if state.tick>=400 and marked and control:
                        dmg_mark=1-marked.hp_percent; dmg_control=1-control.hp_percent
                        report["network_bonus"]={"marked_damage":dmg_mark,"control_damage":dmg_control,
                            "passed":dmg_control>0 and dmg_mark>dmg_control*1.05}
                    if (len(report["checks"])==len(PAIRS) and report.get("network_bonus",{}).get("passed")
                            and report.get("interceptor_rearmed") and report.get("portable_returned_to_at")
                            and report.get("portable_aa_hit") and report.get("at_mode_did_not_hit_air")
                            and len(report.get("range_edge",{}))==len(edge_targets)):
                        report["passed"]=True; break
                    bridge.update_companion_status("ready","Isolated combat verification",muted=True)
                except RuntimeError: pass
                time.sleep(.2)
            report["missing"]=[a for a,_ in PAIRS if a not in report["checks"]]
        except Exception as exc: report["error"]=str(exc)
        finally:
            bridge.close()
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    for label,actor_distance,cell_distance in re.findall(r"CHINA_EDGE\|([a-z]+)\|([0-9.]+)\|([0-9.]+)", (profile/"game.log").read_text()):
        if label not in report.get("range_edge",{}): continue
        check=report["range_edge"][label]
        check.update(distance_source="native actor.CenterPosition and Map.CenterOfCell",
            center_distance_world_units=float(actor_distance),map_cell_distance_world_units=float(cell_distance),
            center_distance_cells=float(actor_distance)/1024,
            range_fraction=float(actor_distance)/check["declared_range_world_units"])
        check["passed"] = check["passed"] and .9 <= check["range_fraction"] <= 1
    report["passed"] = report["passed"] and all(
        c.get("passed") and "range_fraction" in c for c in report.get("range_edge",{}).values())
    (output/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report),flush=True)
    return report["passed"]


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("resources","binaries","content","output"): parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(0 if run(*(getattr(args,k).resolve() for k in ("resources","binaries","content","output"))) else 1)
