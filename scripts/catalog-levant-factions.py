#!/usr/bin/env python3
"""Update the shared guide using the native faction definitions (local only)."""
import json, runpy, subprocess
from pathlib import Path

rules=runpy.run_path(str(Path(__file__).with_name('build-levant-factions.py')))
ROOT=rules['ROOT'];path=ROOT/'OpenRA-AI/catalog/factions.json'
catalog=json.loads(path.read_text(encoding='utf-8'))
catalog['revision']='2026-10-04.1'
catalog['factions']=[f for f in catalog['factions'] if f['id'] not in rules['FACTIONS']]
catalog['units']=[u for u in catalog['units'] if u['factionId'] not in rules['FACTIONS']]
for f,(_,units,title,side) in rules['FACTIONS'].items():
 allied=f=='israel'
 catalog['factions'].append({'id':f,'name':f.capitalize(),'title':title,'tagline':'Protect the formation. Coordinate the strike.' if allied else 'Hold the ground. Move before the counterattack.',
  'story':'A fictional strategy-game roster built around protected armor, forward observation and vulnerable support nodes. Its statistics and abilities are game abstractions.' if allied else 'A fictional strategy-game roster built around light forces, concealed positions and vulnerable support nodes. It depicts gameplay roles, not real-world capability or operational doctrine.',
  'playstyle':'Keep armor, carriers and observers together. Use powered relays to improve firing cycles and service stations to preserve damaged vehicles.' if allied else 'Scout, spread out and control approaches with concealed positions. Guide missiles through spotters and signal posts, then relocate before close attackers or artillery arrive.',
  'strengths':'Durable armor, infantry transport, finite-ammunition aviation, guided fires and local support.' if allied else 'Low-cost forces, stationary concealment, guided rocket pressure and agile coastal craft.',
  'counterplay':'Attack support nodes, cut power and surround expensive units with anti-armor or air threats.' if allied else 'Detect concealed units, destroy signal posts and close the artillery minimum-range gap. Light armor loses concentrated fights.',
  'heroAssetId':f+'-roster','accent':'#80b8ff' if allied else '#b3b881','unitIds':[u[1][2:] for u in units]+[('il' if allied else 'hz')+s for s in ('relay','workshop')],
  'variants':{m:{'status':'implemented','profileId':'world-war-iii' if m=='ra' else 'ra2-modern','description':'Local development roster. Native rules and authored art are present; final art approval, broad balance validation and release confirmation remain pending.','engineFactionId':f,'name':f.capitalize()} for m in ('ra','ra2')}})
 for _,actor,_,name,role,description in units:
  key=actor[2:]
  catalog['units'].append({'id':key,'factionId':f,'name':name,'role':role.replace('-',' ').capitalize(),'story':description,'strengths':'Use the role and support relationships shown in the current mode’s rule-derived roster.','counterplay':'Respect detection, range, armor and support dependencies; the local evaluation tools expose these tradeoffs.','assetIds':[f+'-'+key+'-source',f+'-'+key+'-cameo'],
   'variants':{'ra':{'description':rules['CLASSIC_DESCRIPTIONS'].get(key,description),'actorId':key.upper(),'repository':'engine','rulesPath':f'mods/ra/rules/{f}.yaml','name':name,'role':role.replace('-',' ').capitalize()},'ra2':{'description':description,'actorId':actor,'repository':'mod','rulesPath':f'mods/rtsai/modern-factions/{f}-roster.yaml' if actor not in [u[1] for u in units[4:8]] else f'mods/rtsai/modern-factions/{f}.yaml','name':name,'role':role.replace('-',' ').capitalize()}}})
 for suffix,label in [('relay','Coordination Relay' if allied else 'Signal Post'),('workshop','Field Service Station' if allied else 'Field Workshop')]:
  key=('il' if allied else 'hz')+suffix
  catalog['units'].append({'id':key,'factionId':f,'name':label,'role':'Support structure','story':'A powered, unarmed support building. Local benefits end when it is destroyed or loses power.','strengths':'Supports eligible friendly units inside its visible range. Multiple sources do not multiply the bonus.','counterplay':'Cut power, destroy the exposed node or fight outside its range.','assetIds':[f+'-'+key+'-source',f+'-'+key+'-cameo'],
   'variants':{m:{'actorId':key.upper() if m=='ra' else 'r2'+key,'repository':'engine' if m=='ra' else 'mod','rulesPath':f'mods/ra/rules/{f}.yaml' if m=='ra' else f'mods/rtsai/modern-factions/{f}-roster.yaml','name':label,'role':'Support structure'} for m in ('ra','ra2')}})
for profile in catalog['profiles']:
 profile['factionIds']=list(dict.fromkeys(profile['factionIds']+list(rules['FACTIONS'])))
catalog['sources']['engineCommit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'OpenRA',text=True).strip()
catalog['sources']['modCommit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'RTSAI-Mod',text=True).strip()
path.write_text(json.dumps(catalog,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'factions':len(catalog['factions']),'guideEntries':len(catalog['units'])}))
