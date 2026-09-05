#!/usr/bin/env python3
"""Bounded native combat checks on a disposable Turkey range, never a live match."""
import argparse
from dataclasses import asdict
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

SPEC=importlib.util.spec_from_file_location("turkey_test",Path(__file__).with_name("validate-ra2-turkey.py"))
BASE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(BASE)
PAIRS=(
    ("r2trrifle","e1"),("r2trat","mtnk"),("r2greywolf","e1"),
    ("r2bozkir","mtnk"),("r2aras","e1"),("r2yildirim","mtnk"),
    ("r2gokkalkan","jumpjet"),("r2sancak","e1"),("r2deniz","e1"),
    ("r2kuzgun","mtnk"),("r2turna","mtnk"),("r2sahin","jumpjet"),
    ("r2hisar","e1"),("r2siper","jumpjet"),("r2boran","mtnk"),
    ("r2poyraz","lcrf"),("r2ege","sub"),("r2marmara","lcrf"))


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
        if i>=15: u=25+(i-15)*25; v=108
        if kind=="r2sahin": u,v=48,47  # Near the actual airfield for a bounded rearm cycle.
        # Howitzers need their native minimum distance; others use four cells.
        du,dv=(3,6) if kind=="r2yildirim" else (2,4)
        # RectangularIsometric MPos cells are staggered: horizontal world delta
        # is 724*(2*du + row-parity-change), vertical is 724*dv. (4,4)
        # is 6.324 world cells, outside a six-cell weapon; (4,2) is 5.830.
        if kind in ("r2trat", "r2ege"): du,dv=4,2
        if kind == "r2gokkalkan": du,dv=5,8
        if kind == "r2siper": du,dv=6,10
        actors+=actor("A"+str(i),kind,u,v,"Multi0")+actor("T"+str(i),victim,u+du,v+dv,"Multi1")
        targets[kind]=(u+du,v+dv)
        own_ids[kind]=(u,v)
        lua += [f'A{i}.Stance = "HoldFire"',f'T{i}.Stance = "HoldFire"']
        if kind in ("r2trat","r2ege"):
            lua += [f'print("range:{kind}:" .. tostring(A{i}.CenterPosition) .. ":" .. tostring(T{i}.CenterPosition))']
        if kind in ("r2sahin", "r2gokkalkan", "r2siper", "r2trat"):
            # The jet initially returns to its real airfield. A stationary spotter
            # preserves sight of its target while it makes its attack approach.
            actors += actor("AirSpotter"+str(i), "r2trrifle", u+du+1, v+dv, "Multi0")
            lua += ['AirSpotter'+str(i)+'.Stance = "HoldFire"']
    actors+=actor("CoastalEge","r2ege",25,130,"Multi0")
    actors+=actor("CoastalTarget","lcrf",30,136,"Multi1")
    actors+=actor("CoastalSpotter","r2poyraz",32,136,"Multi0")
    lua += [name+'.Stance = "HoldFire"' for name in ("CoastalEge","CoastalTarget","CoastalSpotter")]
    # Two identical riflemen; only the first target is designated. Compare
    # damage after synchronized firing, rather than inferring from rule text.
    actors+=actor("Marker","r2trdroneop",65,80,"Multi0")
    actors+=actor("MarkedRifle","r2trrifle",67,80,"Multi0")+actor("MarkedTarget","e1",69,84,"Multi1")
    actors+=actor("ControlRifle","r2trrifle",97,80,"Multi0")+actor("ControlTarget","e1",99,84,"Multi1")
    for name in ("Marker","MarkedRifle","MarkedTarget","ControlRifle","ControlTarget"): lua += [name+'.Stance = "HoldFire"']
    text=text.replace("Rules:\n",actors+"Rules:\n")
    # Create the enemy player with an inert bot type. Existing bot modules only
    # activate for normal/medium/rush/turtle/naval, so no AI overrides HoldFire.
    text=text.replace("\tPlayer:\n", "\tPlayer:\n\t\tModularBot@range:\n\t\t\tName: ra2-bot-normal\n\t\t\tType: range-target\n")
    for victim in {v for _,v in PAIRS}:
        text+=f"\t{victim}:\n\t\tHealth:\n\t\t\tHP: 10000\n"
        if victim == "e1": text += "\t\t-TakeCover:\n"
    (target/"map.yaml").write_text(text)
    start=[f"A{i}.Attack(T{i}, {'true' if kind in ('r2sahin','r2kuzgun','r2turna') else 'false'})" for i,(kind,_) in enumerate(PAIRS) if kind != "r2ege"]
    start+=["CoastalEge.Attack(CoastalTarget, false)"]
    script="WorldLoaded = function()\n  "+"\n  ".join(lua)+"\n"
    script+="  Trigger.AfterDelay(40, function() Marker.Attack(MarkedTarget) "+" ".join(start)+" end)\n"
    script+="  Trigger.AfterDelay(80, function() MarkedRifle.Attack(MarkedTarget) ControlRifle.Attack(ControlTarget) end)\nend\n"
    script=script.replace("end)\nend\n", "end)\n  Trigger.AfterDelay(150, function() A16.Attack(T16, false) end)\nend\n")
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
            known_targets={}
            interceptor_ordered=False
            while process.poll() is None and time.monotonic()<end:
                try:
                    state=bridge.observe()
                    enemy={u.actor_id:u for u in state.visible_enemies}
                    own={u.actor_id:u for u in state.units}
                    report["diagnostics"]=[asdict(u) for u in own.values() if u.kind in ("r2sahin","r2trdroneop","r2trat","r2ege")]
                    report["tick"]=state.tick
                    for name,pos in targets.items():
                        if name not in known_targets:
                            target_unit=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==pos),None)
                            if target_unit: known_targets[name]=target_unit.actor_id
                        target_unit=enemy.get(known_targets.get(name))
                        if name == "r2ege" and target_unit and target_unit.hp_percent == 1 and "Underwater" in target_unit.target_types:
                            report["asw_submerged_before_hit"] = True
                        if name in ("r2trat","r2ege"):
                            report.setdefault("range_target_diagnostics",{})[name]=asdict(target_unit) if target_unit else None
                        if target_unit and target_unit.hp_percent<1:
                            report["checks"][name]={"passed":True,"target_hp_fraction":target_unit.hp_percent}
                            if name in ("r2trat","r2ege"):
                                report.setdefault("range_edges",{})[name]={"passed":True,"range_cells":math.hypot(8*724,2*724)/1024,"allow_move":False}
                    interceptor=next((u for u in own.values() if u.kind=="r2sahin"),None)
                    air_target=enemy.get(known_targets.get("r2sahin"))
                    if interceptor and interceptor.ammo<4:
                        report["interceptor_ammo_used"]=True
                    if interceptor and interceptor.ammo==4 and interceptor.idle and report.get("interceptor_ammo_used"):
                        report["interceptor_rearmed"]=True
                    if (interceptor and interceptor.idle and air_target and not interceptor_ordered
                            and "r2sahin" not in report["checks"] and state.tick>100):
                        receipt=bridge.execute_actions("intercept-air-target",state.tick,
                            (ActionCommand("attack",actor_id=interceptor.actor_id,target_actor_id=air_target.actor_id),))
                        report["interceptor_order"]=receipt.as_dict()
                        interceptor_ordered=receipt.accepted
                    marked=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==(69,84)),None)
                    coastal=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==(30,136)),None)
                    if coastal and coastal.hp_percent<1:
                        report["coastal_range_edge"]={"passed":True,"range_cells":math.hypot(10*724,6*724)/1024,"allow_move":False}
                    control=next((u for u in enemy.values() if (u.cell_x,u.cell_y)==(99,84)),None)
                    if state.tick>=400 and marked and control:
                        dmg_mark=1-marked.hp_percent; dmg_control=1-control.hp_percent
                        report["designation"]={"marked_damage":dmg_mark,"control_damage":dmg_control,
                            "passed":dmg_control>0 and dmg_mark>dmg_control*1.05}
                    if (len(report["checks"])==len(PAIRS) and report.get("designation",{}).get("passed")
                            and report.get("interceptor_rearmed") and report.get("coastal_range_edge",{}).get("passed")
                            and report.get("asw_submerged_before_hit")):
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
    (output/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report),flush=True)
    return report["passed"]


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("resources","binaries","content","output"): parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    raise SystemExit(0 if run(*(getattr(args,k).resolve() for k in ("resources","binaries","content","output"))) else 1)
