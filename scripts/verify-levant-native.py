#!/usr/bin/env python3
"""Local native regression scenarios. Emits facts only; never reads image archives.

Disposable fixtures use local installed content through directory links. The
suite checks construction/production, repair, concealment, target eligibility
and actor lifecycle; it is not a faction balance or art-approval certificate.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('local_evals', ROOT / 'RTSAI-Web/tools/native-eval-server.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
defs = runpy.run_path(str(Path(__file__).with_name('build-levant-factions.py')))


def run(mode, naval, output):
    ra2 = mode == 'ra2'
    repo = ROOT / ('RTSAI-Mod' if ra2 else 'OpenRA')
    engine = repo / 'engine' if ra2 else repo
    bh = api.load_harness()
    bh.MOD = 'rtsai' if ra2 else 'ra'
    target = output / f'{mode}-{"naval" if naval else "land"}'
    mods = bh.prepare_resources(target, repo / 'mods')
    support = target / 'support'
    support.mkdir(parents=True, exist_ok=True)
    bh.link_directory(support / 'Content', ROOT / 'OpenRA/Support/Content')
    if not ra2:
        (support / 'settings.yaml').write_text('ExperienceSettings:\n\tProfile: world-war-iii\n', encoding='utf-8')
    fixture = support / bh.user_map_dir(mods / bh.MOD) / 'ai-behavior-arena'
    data = dict(a='r2sadiq' if ra2 and naval else 'r2sang' if ra2 else 'sa_intc' if naval else 'sang', b='r2sadiq' if ra2 and naval else 'r2sang' if ra2 else 'sa_intc' if naval else 'sang', count=1, reps=1, duration=120, candidate='nearest', baseline='hold', opponent='hold')
    api.fixture(fixture, mode, data, 'hold', 0)
    yaml = (fixture / 'map.yaml').read_text(encoding='utf-8')
    for player, faction in [('DuelA', 'israel'), ('DuelB', 'hezbollah')]:
        yaml = yaml.replace(f'Name: {player}\n\t\tFaction: '+('america' if ra2 else 'england'), f'Name: {player}\n\t\tFaction: {faction}')
    (fixture / 'map.yaml').write_text(yaml, encoding='utf-8')
    rosters = {}
    for faction in ['israel', 'hezbollah']:
        units = defs['FACTIONS'][faction][1]
        naval_range = range(10, 13) if faction == 'israel' else range(9, 12)
        actors = [u[1] if ra2 else u[1][2:] for i, u in enumerate(units) if (i in naval_range) == naval]
        if not naval: actors += [('r2il' if faction == 'israel' else 'r2hz')+suffix if ra2 else ('il' if faction == 'israel' else 'hz')+suffix for suffix in ['relay', 'workshop']]
        rosters[faction] = actors
    lua = (Path(__file__).with_name('verify-levant-native.lua')).read_text(encoding='utf-8')
    rules=fixture/'arena-rules.yaml'
    rules.write_text(rules.read_text(encoding='utf-8').replace('Player:\n','Player:\n\t-ConquestVictoryConditions:\n',1),encoding='utf-8')
    values = {'ra2': ra2, 'naval': naval, 'israel': rosters['israel'], 'hezbollah': rosters['hezbollah']}
    def literal(v):
        if isinstance(v, bool): return str(v).lower()
        if isinstance(v, list): return '{'+','.join(json.dumps(x) for x in v)+'}'
        return json.dumps(v)
    lua = lua.replace('__CONFIG__', '{'+','.join(k+'='+literal(v) for k,v in values.items())+'}')
    (fixture / 'arena.lua').write_text(lua, encoding='utf-8')
    env = {k:v for k,v in os.environ.items() if not k.startswith(('OPENRA_AI_', 'RTSAI_'))}
    env['DOTNET_ROLL_FORWARD'] = 'Major'
    env["OPENRA_AI_DISABLE_AUTOSTART"] = "1"
    command = ['dotnet', str(engine/'bin/OpenRA.dll'), f'Engine.EngineDir={engine}', f'Engine.ModSearchPaths={mods}' if not ra2 else f'Engine.ModSearchPaths={mods},{engine/"mods"}', f'Engine.SupportDir={support}', f'Game.Mod={bh.MOD}', 'Game.Platform=Null', 'Game.FetchNews=false', 'Launch.Map=ai-behavior-arena', 'Launch.Benchmark=benchmark-']
    with (target/'engine.log').open('w',encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=engine/'bin', env=env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+180
        logfile = support/'Logs/lua.log'
        while process.poll() is None:
            if logfile.exists() and 'CHECK|DONE' in logfile.read_text(encoding='utf-8',errors='replace'): break
            if time.monotonic()>deadline: break
            time.sleep(.2)
        if process.poll() is None: process.kill()
        process.wait(timeout=10)
    text = logfile.read_text(encoding='utf-8',errors='replace') if logfile.exists() else ''
    rows = [line[line.index('CHECK|'):] for line in text.splitlines() if 'CHECK|' in line]
    result = {'mode': mode, 'naval': naval, 'evidence':'measured', 'ruleCommit':api.commit(repo), 'rulesDirty':bool(subprocess.check_output(['git','-C',str(repo),'status','--porcelain','--','mods'],text=True).strip()), 'checks':rows, 'passed':'CHECK|DONE' in text and not any('|FAIL|' in r for r in rows)}
    (target/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result), flush=True)
    return result['passed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['ra','ra2'], required=True)
    parser.add_argument('--naval', action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'.codex-qa/levant-native')
    args=parser.parse_args()
    sys.exit(0 if run(args.mode,args.naval,args.output.resolve()) else 1)

if __name__ == '__main__': main()
