#!/usr/bin/env python3
"""Private native Iran production, naval movement, weapons and doctrine checks."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.models import ActionCommand
from ra2_iran_assets import UNITS, DEFENSES

SPEC=importlib.util.spec_from_file_location("turkey_fixture",Path(__file__).with_name("validate-ra2-turkey.py"))
BASE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(BASE)
PAIRS=(("r2basij","e1"),("r2toophan","mtnk"),("r2dronecontrol","e1"),("r2shadowone","e1"),
       ("r2karrar","mtnk"),("r2raad","jumpjet"),("r2fajr","mtnk"),("r2coast","gapowr"),
       ("r2mohajer","mtnk"),("r2toufan","e1"),("r2azar","mtnk"),("r2loiter","mtnk"),
       ("r2irbunker","e1"),("r2iraasite","jumpjet"),("r2ircoast","mtnk"),
       ("r2peykaap","lcrf"),("r2ghadir","sub"))
# MPos is NOT a square world-cell grid. Each U step is 1448 world units,
# V steps are 724 with an alternating 724 horizontal offset. These positions
# are 90–99% of the weapon ranges after applying Map.CenterOfCell's transform.
EDGES=(("r2toophan","mtnk",20,20,4,4),("r2fajr","mtnk",50,20,7,2),
       ("r2ircoast","mtnk",80,20,7,2),("r2coast","lcrf",80,95,8,6),
       ("r2peykaap","lcrf",20,105,5,2),("r2raad","jumpjet",20,55,6,6),
       ("r2iraasite","jumpjet",50,55,7,2),("r2peykaap","jumpjet",50,105,4,2),
       ("r2mohajer","mtnk",80,55,4,2),("r2toufan","e1",100,55,4,2),
       ("r2azar","mtnk",100,20,4,4))
EDGE_RANGES=(7,11,11,13,8,10,11,6,6,6,7)


def edge_distances():
    result={}
    for i,(actor,victim,_,v,du,dv) in enumerate(EDGES):
        distance=math.hypot((2*du+(v+dv)%2-v%2)*724,dv*724)/1024
        fraction=distance/EDGE_RANGES[i]
        assert .9<=fraction<=1,(actor,distance,fraction)
        result[actor+("-aa" if victim=="jumpjet" else "")]={"range_cells":distance,"declared_range":EDGE_RANGES[i],
            "range_fraction":fraction,"allow_move":i>=8}
    return result


def fixture(resources,profile,mode,scene="infantry"):
    target=BASE.fixture(resources,profile)
    text=(target/"map.yaml").read_text().replace("Faction: turkey","Faction: iran")
    for old,new in (("gacnst","nacnst"),("gaweap","naweap"),("gapowr","napowr"),("garefn","narefn"),
                    ("gaairc","naradr"),("gapile","nahand"),("gatech","natech"),("gayard","nayard")):
        text=text.replace(": "+old+"\n",": "+new+"\n")
    # Extra real reactors keep the prebuilt range powered throughout defense production.
    text=text.replace("Rules:\n","\tRangePower1: napowr\n\t\tOwner: Multi0\n\t\tLocation: 33,-10\n\tRangePower2: napowr\n\t\tOwner: Multi0\n\t\tLocation: 25,-10\nRules:\n")
    targets={}; lua=[]
    def actor(name,kind,u,v,owner="Multi0"):
        x,y=u+(v+1)//2,v//2-u
        return f"\t{name}: {kind}\n\t\tOwner: {owner}\n\t\tLocation: {x},{y}\n"
    if mode=="edges":
        actors=""; lua=[]
        for i,(kind,victim,u,v,du,dv) in enumerate(EDGES):
            actors+=actor("Edge"+str(i),kind,u,v)+actor("Target"+str(i),victim,u+du,v+dv,"Multi1")
            # Long range must be tested with a stationary spotter so visibility
            # cannot shorten the attack and masquerade as a missile range bug.
            spotter="r2peykaap" if v+dv>=100 else "r2basij"
            actors+=actor("Spotter"+str(i),spotter,u+du+1,v+dv)
            for prefix in ("Edge","Target","Spotter"): lua.append(f'{prefix}{i}.Stance = "HoldFire"')
            targets[kind+("-aa" if victim=="jumpjet" else "")]=(u+du,v+dv)
        text=text.replace("Rules:\n",actors+"Rules:\n")
        text=text.replace("\tPlayer:\n","\tPlayer:\n\t\tModularBot@range:\n\t\t\tName: ra2-bot-normal\n\t\t\tType: range-target\n")
        for victim in {item[1] for item in EDGES}:
            text+=f"\t{victim}:\n\t\tHealth:\n\t\t\tHP: 10000\n"
            if victim=="e1": text+="\t\t-TakeCover:\n"
        script="WorldLoaded = function()\n  "+"\n  ".join(lua)+"\n"
        script+="  Trigger.AfterDelay(40, function() "+" ".join(f"Edge{i}.Attack(Target{i}, {'true' if i>=8 else 'false'})" for i in range(len(EDGES)))+" end)\nend\n"
        (target/"review.lua").write_text(script)
    if mode=="visual":
        text=text.replace(",-10\n",",-30\n")
        text=text.replace("Location: 25,-30", "Location: 25,-10").replace("Location: 33,-30", "Location: 33,-10")
        actors=""
        if scene=="infantry":
            for i,kind in enumerate(("e2","r2basij","r2toophan","r2dronecontrol","r2shadowone")):
                actors+=actor("Review"+str(i),kind,32+i*2,64)
            for i,kind in enumerate(DEFENSES): actors+=actor("Defense"+str(i),kind,34+i*3,73)
        else:
            lineup=("r2karrar","r2coast","r2toufan","r2azar","r2loiter") if scene=="armor" else ("r2peykaap","r2ghadir")
            for i,kind in enumerate(lineup):
                actors+=actor("Review"+str(i),kind,32+i*2,66 if scene=="armor" else 110)
        text=text.replace("Rules:\n",actors+"Rules:\n")
        focus="Review2" if scene!="navy" else "Review0"
        (target/"review.lua").write_text('WorldLoaded = function() Camera.Position = '+focus+'.CenterPosition end\n')
        if scene=="armor":
            # Static review only; combat mode retains continuous fixed-wing flight.
            text+="\tr2azar:\n\t\tAircraft:\n\t\t\tIdleSpeed: 0\n"
    if mode=="combat":
        actors=""
        for i,(kind,victim) in enumerate(PAIRS):
            u,v=8+i%6*20,14+i//6*25
            if i>=15: u,v=25+(i-15)*35,108
            du,dv=(3,6) if kind in ("r2fajr","r2coast") else (2,4)
            actors+=actor("A"+str(i),kind,u,v)+actor("T"+str(i),victim,u+du,v+dv,"Multi1")
            targets[kind]=(u+du,v+dv)
            lua.append(f'A{i}.Stance = "HoldFire"')
            if victim!="gapowr": lua.append(f'T{i}.Stance = "HoldFire"')
            if kind=="r2loiter":
                actors+=actor("LoiterSpotter","r2basij",u+du+1,v+dv)
                lua.append('LoiterSpotter.Stance = "HoldFire"')
        # Compare identical native drones, differing only by nearby coordinator.
        for name,kind,u,v,owner in (("Coordinator","r2dronecontrol",12,83,"Multi0"),
            ("Guided","r2mohajer",15,83,"Multi0"),("GuidedTarget","mtnk",17,87,"Multi1"),
            ("Unguided","r2mohajer",55,83,"Multi0"),("UnguidedTarget","mtnk",57,87,"Multi1"),
            ("Emplaced","r2toophan",82,83,"Multi0"),("EmplacedTarget","mtnk",84,87,"Multi1"),
            ("MobileControl","r2toophan",112,83,"Multi0"),("MobileTarget","mtnk",114,87,"Multi1"),
            ("AABoat","r2peykaap",90,110,"Multi0"),("BoatTarget","jumpjet",92,114,"Multi1"),
            ("Saboteur","r2shadowone",9,90,"Multi0")):
            actors+=actor(name,kind,u,v,owner)
            lua.append(name+'.Stance = "HoldFire"')
        actors+=actor("SabotageTarget","gapowr",10,92,"Multi1")
        targets.update(guided=(17,87),unguided=(57,87),emplaced=(84,87),mobile=(114,87),peykaap_aa=(92,114),shadow_charge=(10,92))
        text=text.replace("Rules:\n",actors+"Rules:\n")
        text=text.replace("\tPlayer:\n","\tPlayer:\n\t\tModularBot@range:\n\t\t\tName: ra2-bot-normal\n\t\t\tType: range-target\n")
        for kind in {v for _,v in PAIRS}:
            text+=f"\t{kind}:\n\t\tHealth:\n\t\t\tHP: 10000\n"
            if kind=="e1": text+="\t\t-TakeCover:\n"
        # Simulate only the movement condition, holding position/firing geometry
        # constant. This isolates reload bonus from movement's normal lost shots.
        text+="\tr2toophan:\n\t\tExternalCondition@range-moving:\n\t\t\tCondition: moving\n"
        script="WorldLoaded = function()\n  "+"\n  ".join(lua)+"\n"
        script+='  MobileControl.GrantCondition("moving")\n'
        commands=" ".join(f"A{i}.Attack(T{i})" for i in range(len(PAIRS)))
        script+="  Trigger.AfterDelay(40, function() "+commands+" Guided.Attack(GuidedTarget) Unguided.Attack(UnguidedTarget) Emplaced.Attack(EmplacedTarget) MobileControl.Attack(MobileTarget) AABoat.Attack(BoatTarget) Saboteur.Attack(SabotageTarget) end)\nend\n"
        (target/"review.lua").write_text(script)
    (target/"map.yaml").write_text(text)
    return targets


def run(resources,binaries,content,output,mode,scene="infantry"):
    output.mkdir(parents=True,exist_ok=True)
    profile=Path(tempfile.mkdtemp(prefix="iran-",dir=output))
    (profile/"Content").symlink_to(content,target_is_directory=True)
    targets=fixture(resources,profile,mode,scene)
    with socket.socket() as sock: sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    env={**os.environ,"OPENRA_AI_COMPANION":"1","OPENRA_AI_COMPANION_READY":"1","OPENRA_AI_STARTUP_ENABLED":"1",
        "OPENRA_AI_STARTUP_AUTO_ACT":"0","OPENRA_AI_STARTUP_MUTED":"1","OPENRA_AI_GRPC_PORT":str(port)}
    cmd=["dotnet",str(binaries/"OpenRA.dll"),f"Engine.EngineDir={resources}",f"Engine.SupportDir={profile}",
         "Game.Mod=ra2","Game.FetchNews=false","Launch.Map=modern-art-review"]
    cmd += ["Graphics.Mode=Windowed","Graphics.WindowedSize=1440,900","Graphics.ViewportDistance=Close"] if mode=="visual" else ["Game.Platform=Null"]
    if mode in ("combat","edges"): cmd.append("Launch.Bots=Multi1:range-target")
    report={"passed":False,"profile":str(profile),"mode":mode,"checks":{}}
    if mode=="edges": report["edge_distances"]=edge_distances()
    with (profile/"game.log").open("w") as log:
        process=subprocess.Popen(cmd,cwd=binaries,env=env,stdout=log,stderr=subprocess.STDOUT)
        bridge=OpenRABridge(f"127.0.0.1:{port}",timeout=1)
        try:
            deadline=time.monotonic()+160
            phase="queue"; placed=set(); cleared=set(); known={}; moved=set(); seen_loiter=False
            while process.poll() is None and time.monotonic()<deadline:
                try:
                    state=bridge.observe(); units={u.kind:u for u in state.units}; buildings={u.kind:u for u in state.buildings}
                    report["tick"]=state.tick
                    if mode=="visual":
                        if state.tick>=60:
                            frame=bridge.capture_frame()
                            assert frame.scope=="rendered-player-viewport-fog-respecting"
                            (output/"native-iran-review.png").write_bytes(frame.png)
                            report.update(passed=True,scope=frame.scope)
                            break
                    elif mode=="production":
                        report["last_state"]={"units":sorted(units),"buildings":sorted(buildings),"production":state.production}
                        if phase=="queue":
                            available=set(state.available_production); missing=set(UNITS+DEFENSES)-available
                            if missing: raise ValueError("Missing production: "+str(missing))
                            forbidden={"e2","shk","flakt","htnk","apoc","zep","sub","hyd","sqd","nalasr","naflak","tesla","r2qilin","r2bozkir"}&available
                            if forbidden: raise ValueError("Foreign/replaced choices: "+str(forbidden))
                            report["available"]=sorted(available)
                            commands=[ActionCommand("train",item_type=a) for a in UNITS]+[ActionCommand("build",item_type=a) for a in DEFENSES]
                            for start in range(0,len(commands),12):
                                receipt=bridge.execute_actions("iran-production-"+str(start),state.tick,tuple(commands[start:start+12]))
                                if not receipt.accepted: raise ValueError(str(receipt.as_dict()))
                            phase="produce"
                        for a in DEFENSES:
                            if a in buildings: placed.add(a)
                            elif a not in placed: bridge.execute_actions("place-"+a+"-"+str(state.tick),state.tick,(ActionCommand("place_building",item_type=a),))
                        for i,a in enumerate(("r2karrar","r2raad","r2fajr","r2coast")):
                            if a in units and a not in cleared:
                                if bridge.execute_actions("clear-"+a,state.tick,(ActionCommand("move",actor_id=units[a].actor_id,target_x=20+i*5,target_y=65),)).accepted: cleared.add(a)
                        if set(UNITS)<=units.keys() and len(placed)==3 and phase=="produce":
                            report["produced"]={a:{"name":state.actor_name(a),"air":units[a].can_target_air,"ground":units[a].can_target_ground} for a in UNITS}
                            if not units["r2peykaap"].can_target_air or not units["r2peykaap"].can_target_ground:
                                raise ValueError("Missile craft bridge metadata omits a secondary weapon domain")
                            if not units["r2coast"].can_target_ground:
                                raise ValueError("Bridge metadata omits coastal launcher's structure target domain")
                            if not buildings["r2iraasite"].can_target_air or not buildings["r2ircoast"].can_target_ground:
                                raise ValueError("Bridge metadata omits defense weapon domains")
                            for i,a in enumerate(("r2peykaap","r2ghadir")):
                                bridge.execute_actions("water-"+a,state.tick,(ActionCommand("move",actor_id=units[a].actor_id,target_x=25+i*12,target_y=115),))
                            phase="water"
                        if phase=="water":
                            for i,a in enumerate(("r2peykaap","r2ghadir")):
                                if (units[a].cell_x,units[a].cell_y)==(25+i*12,115): moved.add(a)
                            if len(moved)==2:
                                report.update(passed=True,defenses=sorted(placed),water_movement=sorted(moved)); break
                    else:
                        enemy={u.actor_id:u for u in state.visible_enemies+state.visible_enemy_buildings}
                        for name,pos in targets.items():
                            if name not in known:
                                unit=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==pos),None)
                                if not unit and name in ("r2coast","shadow_charge"):
                                    unit=next((u for u in enemy.values() if u.kind=="gapowr" and abs(u.cell_x-pos[0])+abs(u.cell_y-pos[1])<=3),None)
                                if unit: known[name]=unit.actor_id
                            unit=enemy.get(known.get(name))
                            if unit and unit.hp_percent<1: report["checks"][name]=1-unit.hp_percent
                        if mode=="edges" and all(name in report["checks"] for name in targets):
                            report["passed"]=True; break
                        if "r2loiter" in units: seen_loiter=True
                        report["loiter_expended"]=seen_loiter and "r2loiter" not in units and "r2loiter" in report["checks"]
                        if state.tick>=1100:
                            checks=report["checks"]
                            report["guidance_bonus"]=checks.get("guided",0)>checks.get("unguided",0)*1.05>0
                            report["emplacement_bonus"]=checks.get("emplaced",0)>checks.get("mobile",0)*1.05>0
                            if all(a in checks for a in targets) and report["guidance_bonus"] and report["emplacement_bonus"] and report["loiter_expended"]:
                                report["passed"]=True; break
                    report["phase"]=phase
                    bridge.update_companion_status("ready","Private Iran verification",muted=True)
                except RuntimeError as exc: report["last_connection_error"]=str(exc)
                time.sleep(.15)
            if not report["passed"]: report["error"]="Process ended or deadline reached"
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
    parser.add_argument("--mode",choices=("production","combat","edges","visual"),default="production")
    parser.add_argument("--scene",choices=("infantry","armor","navy"),default="infantry")
    args=parser.parse_args()
    raise SystemExit(0 if run(*(getattr(args,k).resolve() for k in ("resources","binaries","content","output")),args.mode,args.scene) else 1)
