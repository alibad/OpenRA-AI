#!/usr/bin/env python3
"""Build two fictional RTS faction packs locally from project-owned foundations.

No external services, game asset archives, models or credentials are opened.
Game rules are generated separately for each engine; balance is provisional.
"""
from __future__ import annotations
import json, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / 'RTSAI-Mod/mods/rtsai'
RA = ROOT / 'OpenRA/mods/ra'
PACK = MOD / 'modern-factions'

# Source actor, new actor, Classic foundation, visible name, role, description.
ISRAEL = [
 ('r2sang','r2ilrifle','SANG','Rifle Team','line-infantry','Three-round burst infantry. Deploy to brace: +18% range, 20% faster fire and 28% less incoming damage. Moving ends the brace. Weak against armor and aircraft.'),
 ('r2saat','r2ilat','SAAT','Anti-Armor Team','anti-armor','Guided anti-armor missiles with a two-cell minimum range. Marked targets take extra damage. Screen against infantry and close rushes.'),
 ('r2sajtac','r2ilobserver','SAJTAC','Forward Observer','support','Marks ground and naval targets for eight seconds. Only this faction\'s guided weapons gain bonus damage. Detects cloaked units; no direct damage.'),
 ('r2falcon','r2ilrecon','FALCON1','Recon Specialist','line-infantry','One elite reconnaissance specialist with a precision double-tap, demolition ability and a timed precision air strike. Fragile against concentrated fire.'),
 ('r2m1a2s','r2merkava','M1A2S','Merkava Battle Tank','main-battle-tank','Durable armored anchor with a 120 mm cannon. Benefits from a powered coordination relay. Expensive and slow; vulnerable to air attacks and flanking anti-armor teams.'),
 ('r2sads','r2ilshield','SADS','Mobile Air Shield','anti-air','Long-range radar-guided anti-air missiles. Cannot engage ground targets. Protect with infantry and armor.'),
 ('r2caesar','r2ilhowitzer','ARTY','Siege Howitzer','artillery','Tracked artillery with a four-cell minimum range. Guided shells hit marked targets harder. Requires an escort and room to withdraw.'),
 ('r2bradley','r2namer','APC','Namer Support Carrier','transport','Protected carrier for five infantry, with a cannon and a slow-reloading anti-armor missile. Durable but expensive. Unload infantry before an ambush.'),
 ('r2f15sa','r2ilfalcon','F15SA','Falcon Multirole Jet','interceptor','Multirole aircraft with separate air and ground missile magazines. Returns to its air service building to rearm. Requires advanced technology.'),
 ('r2ah64sa','r2ilgunship','AH64SA','Escort Gunship','strike-aircraft','Attack helicopter with a chain gun and guided anti-armor rockets. Marked targets take extra rocket damage. Keep clear of anti-air coverage.'),
 ('r2sadiq','r2ilpatrol','SA_INTC','Coastal Patrol Craft','naval-screen','Fast cannon patrol craft. Sonar reveals submarines. Screens light boats but loses to heavy ships.'),
 ('r2riyadh','r2ilfrigate','SA_FRGT','Shield Frigate','anti-submarine','Naval gun, anti-air and depth charges. Limited interceptor magazine deflects missiles. Active radar increases coverage but reveals the ship.'),
 ('r2jubail','r2iltender','SA_FSS','Fleet Support Tender','support','Unarmed fleet support. Nearby eligible ships repair and frigate interceptors reload faster. Escort this vulnerable ship.'),
 ('r2saguard','r2ilsentry','PBOX','Sentry Emplacement','line-infantry','Powered anti-infantry defense. Weak against armor, artillery and aircraft.'),
 ('r2sapatriot','r2ilbattery','SAM','Interceptor Battery','anti-air','Powered long-range anti-air defense with a two-cell minimum range. Cannot fire at ground targets. This is an aircraft defense, not a universal missile shield.'),
 ('r2satow','r2ilatpost','GUN','Anti-Armor Emplacement','anti-armor','Powered guided anti-armor missiles with a two-cell minimum range. Marked ground and naval targets take extra damage. Close infantry and artillery counter it.'),
]
HEZBOLLAH = [
 ('r2ymr','r2hzrifle','YMR','Line Fighter','line-infantry','Inexpensive rifle infantry. Conceals while stationary; moving, firing or taking damage reveals it. Detectors and artillery defeat isolated positions.'),
 ('r2yrpg','r2hzat','YRPG','Ridge Missile Team','anti-armor','Light anti-armor missile infantry. A signal post or scout improves range and reload. Vulnerable to infantry, detectors and air attacks.'),
 ('r2yspot','r2hzspotter','YSPOT','Field Spotter','support','Reconnaissance specialist who detects cloaked units and guides nearby eligible missile teams and vehicles. A weak weapon makes escorts essential.'),
 ('r2wadighost','r2hzscout','WADIGHOST','Cedar Scout','line-infantry','One concealed scout with a suppressed carbine and demolition ability. Stationary concealment breaks when firing, moving or damaged. Vulnerable once detected.'),
 ('r2technical','r2hztechnical','TECH','Cedar Technical','line-infantry','Fast and inexpensive machine-gun vehicle. Strong against exposed infantry, weak against armor and air attacks.'),
 ('r2ytechrr','r2hzrecoilless','TECH','Recoilless Technical','anti-armor','Mobile anti-armor fire on a fragile chassis. Signal coverage improves range and reload. Infantry and aircraft punish exposed vehicles.'),
 ('r2yzu','r2hzescort','FTRK','Escort Gun Truck','anti-air','Fragile mobile anti-air escort. Its ground fire discourages infantry; tanks and artillery counter it.'),
 ('r2ymlr','r2hzrockets','YMLR','Mobile Rocket Battery','artillery','Long-range rocket artillery with a minimum range and a slow reload. Must stop to set up its stabilized firing cycle. Scouts or signal posts improve guided fire; close attacks force withdrawal.'),
 ('r2samad','r2hzdrone','SAMAD','Loiter Drone','strike-aircraft','One-way airborne attack that consumes the drone. Scout the target first. Anti-air fire destroys it before impact.'),
 ('r2hodeidah','r2hzmissileboat','YE_MSLC','Coastal Missile Boat','naval-screen','Light guided-missile craft. Coverage from a scout boat supports coordinated fire; poor armor demands spacing and an escort.'),
 ('r2sahaab','r2hzskiff','YE_USV','Attack Skiff','naval-screen','Inexpensive one-way attack boat. Requires a reachable water target and is consumed on impact. Patrol screens and concentrated fire counter it.'),
 ('r2mokha','r2hzsurvey','YE_SURVE','Coastal Survey Boat','support','Light patrol and reconnaissance craft with sonar and fleet guidance. Prioritize its sensors; heavy warships outgun it.'),
 ('r2ybunker','r2hzbunker','HBOX','Concealed Bunker','line-infantry','Stationary concealed machine-gun defense. Firing or taking damage reveals it. Detection and artillery counter the position.'),
 ('r2yzunest','r2hzaanest','SAM','Short-Range AA Nest','anti-air','Low-cost anti-air emplacement. Cannot substitute for armor defense. Artillery attacks outside its range.'),
 ('r2ycoastal','r2hzcoastal','GUN','Coastal Missile Emplacement','anti-armor','Concealed missile defense against ground vehicles and ships. Minimum range leaves a close-attack window. Detection and infantry counter it.'),
]
CLASSIC_DESCRIPTIONS = {'ilat': 'Guided anti-armor infantry. Marks from a forward observer improve guided fire. Screen against infantry and close attacks.', 'ilobserver': 'Observer with a light defensive weapon, target marking and cloak detection. Supports guided anti-armor weapons; vulnerable alone.', 'ilhowitzer': 'Tracked long-range artillery. Requires an escort and space to withdraw; aircraft and close attacks counter it.', 'ilfrigate': 'Naval cannon, anti-air missiles and depth charges. Limited interceptor ammunition and active radar provide fleet protection. Sensor mode reveals the ship.', 'iltender': 'Unarmed fleet support. Repairs eligible nearby ships and supplies fleet guidance. Escort this vulnerable ship.', 'hzrockets': 'Long-range rocket artillery on a fragile mobile chassis. Spotter guidance improves coordinated fire; vulnerable when approached closely.', 'hzbunker': 'Concealed defensive bunker with room for infantry. Attacking and damage reveal it. Detection and artillery counter it.', 'hzcoastal': 'Concealed anti-armor missile emplacement able to engage vehicles and ships. Detection, infantry and artillery counter it.', 'ilbattery': 'Powered anti-air missile defense. Protects the base against aircraft; cannot fire at ground units.'}
FACTIONS = {'israel': ('saudi', ISRAEL, 'Precision support', 'Allies'), 'hezbollah': ('yemen', HEZBOLLAH, 'Concealed defense', 'Soviets')}

def read(path): return path.read_text(encoding='utf-8')
def normalized(text):
 # Merge repeated local override nodes before strict native MiniYaml loading.
 def merge(nodes):
  out={}
  for key,value,children in nodes:
   if key in out:
    previous=out[key]; previous[1]=value or previous[1]; previous[2]+=children
   else:out[key]=[key,value,children]
  return [[key,value,merge(children)] for key,value,children in out.values()]
 root=[];stack=[(-1,root)]
 for line in text.splitlines():
  if not line.strip() or line.lstrip().startswith('#'):continue
  depth=len(line)-len(line.lstrip('\t'));key,_,value=line.strip().partition(':')
  while stack[-1][0]>=depth:stack.pop()
  node=[key,value.strip(),[]];stack[-1][1].append(node);stack.append((depth,node[2]))
 def render(nodes,depth=0):
  return ''.join('\t'*depth+k+':'+(' '+v if v else '')+'\n'+render(c,depth+1) for k,v,c in nodes)
 return render(merge(root))

def write(path, text):
 path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(text.rstrip()+'\n', encoding='utf-8')
def blocks(text):
 return {m[1]: m[0] for m in re.finditer(r'^([^\s#][^:\n]*):[^\n]*\n(?:\t[^\n]*\n|\n|#[^\n]*\n)*', text, re.M)}
def rewrite(text, replacements):
 return re.sub('|'.join(re.escape(x) for x in sorted(replacements, key=len, reverse=True)), lambda m: replacements[m[0]], text)
def add_manifest(path, anchor, new):
 text=read(path)
 if new.strip() not in text: write(path,text.replace(anchor,anchor+'\n'+new))

def support_rules(faction, mode):
 ra2 = mode=='ra2'; prefix='r2il' if faction=='israel' else 'r2hz'
 if not ra2: prefix=prefix[2:].upper()
 relay=prefix+('relay' if ra2 else 'RELAY'); workshop=prefix+('workshop' if ra2 else 'WORKSHOP')
 allied=faction=='israel'; condition=f'{faction}-linked' if allied else 'r2-hz-guidance' if ra2 else 'redsea-spotted'
 base='^R2IsraelDefense' if allied and ra2 else '^R2HezbollahDefense' if ra2 else '^Defense'
 health=420 if ra2 else 42000
 queue='Support' if ra2 else 'Defense'
 requirements=f'~faction.{faction}, radar' if ra2 else f'~structures.{faction}, dome, ~techlevel.medium'
 icon=f'ra2|modern-factions/icons/{relay}.png' if ra2 else 'pboxicon.shp'
 text=f'''{relay}:
\tInherits: {base}
\tTooltip:
\t\tName: levant-{relay.lower()}-name
\tBuildable:
\t\tQueue: {queue}
\t\tPrerequisites: {requirements}
\t\tBuildPaletteOrder: 65
\t\tDescription: levant-{relay.lower()}-description
\tValued:
\t\tCost: 750
\tHealth:
\t\tHP: {health}
\t-Armament:
\t-AttackTurreted:
\t-WithSpriteTurret:
\t-Turreted:
\t-AutoTarget:
\t-AutoTargetPriority@DEFAULT:
\t-AutoTargetPriority@ATTACKANYTHING:
\tRenderSprites:
\t\tImage: {relay.lower()}
\tPower:
\t\tAmount: -35
\tGrantConditionOnPowerState@LOWPOWER:
\t\tCondition: lowpower
\t\tValidPowerStates: Low, Critical
\tProximityExternalCondition@link:
\t\tCondition: {condition}
\t\tRange: 6c0
\t\tValidRelationships: Ally
\t\tRequiresCondition: !lowpower && !build-incomplete
\tDetectCloaked:
\t\tRange: 5c0
\t\tRequiresCondition: !lowpower && !build-incomplete
\tWithRangeCircle@link:
\t\tRange: 6c0
\t\tColor: {'80B8FF80' if allied else 'B3B88180'}
\tStrategicRole:
\t\tRoles: support
\t\tDomain: defense

{workshop}:
\tInherits: {relay}
\tTooltip:
\t\tName: levant-{workshop.lower()}-name
\tBuildable:
\t\tBuildPaletteOrder: 66
\t\tDescription: levant-{workshop.lower()}-description
\tValued:
\t\tCost: 900
\t-ProximityExternalCondition@link:
\t-DetectCloaked:
\tProximityExternalCondition@repair:
\t\tCondition: {faction}-repair
\t\tRange: 4c0
\t\tValidRelationships: Ally
\t\tRequiresCondition: !lowpower && !build-incomplete
\tWithRangeCircle@link:
\t\tRange: 4c0
\tRenderSprites:
\t\tImage: {workshop.lower()}
'''
 if not ra2:
  text=re.sub(r'^\t-(?:Armament|AttackTurreted|WithSpriteTurret|Turreted|AutoTarget|AutoTargetPriority@DEFAULT|AutoTargetPriority@ATTACKANYTHING):\n','',text,flags=re.M)
  text=text.replace(f'\tInherits: {base}\n',f'\tInherits: {base}\n\t-RenderRangeCircle:\n',1)
 return text

def build_ra2(faction, source, units):
 old=source.capitalize(); title=faction.capitalize()
 mapping={a:b for a,b,*_ in units}
 # Scope every status/weapon to its new faction; no hidden cross-faction laser bonus.
 weapon_sources=blocks(read(PACK/f'{source}-weapons.yaml'))
 mapping.update({k:'R2IL'+k[2:] if faction=='israel' else 'R2HZ'+k[2:] for k in weapon_sources})
 mapping.update({f'^R2{old}':f'^R2{title}',f'R2{old}':f'R2{title}',source:faction,old:title})
 if faction=='israel':
  mapping.update({'r2f15strike':'r2ilstrike','R2Lased':'R2ILMarked','r2-lased':'r2-il-marked','R2LASED':'R2ILMARKED','r2-fleet-support':'r2-il-fleet-support','FalconPrecisionStrike':'IsraelPrecisionStrike'})
 else:
  mapping.update({'r2-ye-guidance':'r2-hz-guidance','r2-ye-fleet':'r2-hz-fleet','r2-ye-':'r2-hz-'})
 for ext in ('.yaml','-roster.yaml','-ai.yaml','-roles.yaml','-weapons.yaml','-sequences.yaml','-roster-sequences.yaml','-voxels.yaml'):
  text=rewrite(read(PACK/(source+ext)).rstrip()+'\n\n',mapping)
  # Keep original-project generic effects and sounds, not another faction's voices.
  text=text.replace('modern-factions/audio/'+faction, 'modern-factions/audio/'+source)
  if ext=='.yaml':
   text=text.replace(f'Name: ra2-modern-{faction}-name',f'Name: ra2-modern-{faction}-name')
  if ext=='-roster.yaml' or ext=='.yaml':
   for a,b,classic,name,role,description in units:
    block=blocks(text).get(b)
    if block:
     updated=re.sub(r'(\tBuildable:\n(?:\t\t[^\n]*\n)*?)\t\tDescription: [^\n]*',lambda m:m[1]+f'\t\tDescription: levant-{b}-description',block)
     updated=re.sub(r'(\tTooltip:\n)\t\tName: [^\n]*',rf'\1\t\tName: levant-{b}-name',updated)
     if faction=='israel' and role not in ('anti-submarine','naval-screen') and ('\tMobile:' in updated or 'Infantry' in updated):
      updated+=f'\tInherits@coordination: ^LevantIsraelCoordination\n'
     if role in ('main-battle-tank','transport') and faction=='israel':
      updated=re.sub(r'(\tHealth:\n\t\tHP: )\d+',lambda m:m[1]+('640' if role=='main-battle-tank' else '420'),updated)
      updated=re.sub(r'(\tValued:\n\t\tCost: )\d+',lambda m:m[1]+('1450' if role=='main-battle-tank' else '1050'),updated)
     if '\tMobile:' in updated:
      updated+=f'\tExternalCondition@repair:\n\t\tCondition: {faction}-repair\n\tChangesHealth@field:\n\t\tStep: 2\n\t\tDelay: 25\n\t\tStartIfBelow: 70\n\t\tRequiresCondition: {faction}-repair\n'
     if b=='r2namer':
      updated=updated.replace('Type: Light','Type: Heavy').replace('Speed: 110','Speed: 85')
     if b=='r2hzrockets':
      updated+='\tGrantConditionOnMovement@setup:\n\t\tCondition: moving\n\tReloadDelayMultiplier@setup:\n\t\tModifier: 70\n\t\tRequiresCondition: !moving\n\tWithTextDecoration@setup:\n\t\tText: SET\n\t\tColor: B3B881\n\t\tRequiresCondition: !moving\n\t\tRequiresSelection: true\n'
     text=text.replace(block,updated)
  if ext=='-roster.yaml': text+='\n'+support_rules(faction,'ra2')
  if ext=='-roster.yaml':
   for _,actor,*_ in units:
    text=text.replace(f'Name: ra2-{actor}-name',f'Name: levant-{actor}-name')
  write(PACK/(faction+ext),text)
 # Reuse appropriate local stock voice families; country-specific recorded lines are not relabeled.
 voices=''
 for i,(_,actor,*_) in enumerate(units):
  voices+=f'{actor}:\n\tVoiced:\n\t\tVoiceSet: {"LevantInfantryVoice" if i<4 else "LevantVehicleVoice"}\n\n'
 write(PACK/f'{faction}-audio.yaml',voices)
 locale=f'ra2-modern-{faction}-name = {title}\nra2-modern-{faction}-description = Fictional RTS faction: {"precision armor, protected support and guided fire" if faction=="israel" else "light mobile forces, concealed defenses and guided rockets"}.\n    Includes economy, production, land, air, naval and support buildings.\n    New local development roster; balance and final art approval pending.\n\n'
 for _,actor,_,name,_,description in units: locale+=f'levant-{actor}-name = {name}\nlevant-{actor}-description = {description}\n\n'
 # Inherited support-power and aircraft proxy keys still need localized names.
 original=rewrite(read(PACK/f'{source}-messages.ftl'),mapping)
 original=re.sub(r'^ra2-modern-'+faction+r'-(?:name|description) =.*(?:\n    .*?)*\n', '', original, flags=re.M)
 locale+=original
 for suffix,label,desc in [('relay','Coordination Relay' if faction=='israel' else 'Signal Post','Powered six-cell support and five-cell cloak detection. '+('Eligible infantry and vehicles reload 15% faster; bonuses do not stack.' if faction=='israel' else 'Eligible guided units gain range and reload bonuses; bonuses do not stack.')),('workshop','Field Service Station' if faction=='israel' else 'Field Workshop','Powered four-cell repair zone for eligible vehicles. Repairs two health per second only below 70% health. Bonuses do not stack; protect this unarmed structure.')]:
  actor=('r2il' if faction=='israel' else 'r2hz')+suffix
  locale+=f'levant-{actor}-name = {label}\nlevant-{actor}-description = {desc}\n'
 write(PACK/f'{faction}-messages.ftl',locale)
 # Only project-authored packages are copied, never stock content or archives.
 owned=PACK/f'{source}-art'; out=PACK/f'{faction}-art'; out.mkdir(exist_ok=True)
 for path in owned.iterdir():
  if path.suffix in ('.pal','.shp'): shutil.copy2(path,out/rewrite(path.name,mapping))
 for path in (PACK/'voxels').iterdir():
  if path.suffix in ('.vxl','.hva') and any(path.stem.startswith(a) for a,_,*_ in units):
   shutil.copy2(path,path.with_name(rewrite(path.name,mapping)))
 for a,b,*_ in units:
  if (PACK/'icons'/f'{a}.png').exists(): shutil.copy2(PACK/'icons'/f'{a}.png',PACK/'icons'/f'{b}.png')
 for ext,section in [('.yaml','Rules'),('-roster.yaml','Rules'),('-ai.yaml','Rules'),('-roles.yaml','Rules'),('-audio.yaml','Rules'),('-sequences.yaml','Sequences'),('-roster-sequences.yaml','Sequences'),('-voxels.yaml','VoxelSequences'),('-weapons.yaml','Weapons'),('-messages.ftl','FluentMessages')]:
  anchor=f'\tra2|modern-factions/{source}{ext}'
  add_manifest(MOD/'mod.yaml',anchor,f'\tra2|modern-factions/{faction}{ext}')

def classic(faction, source, units):
 title=faction.capitalize(); allied=faction=='israel'; side='allies' if allied else 'soviet'
 prefix='IL' if allied else 'HZ'
 combined={**blocks(read(RA/'rules/red-sea.yaml')),**blocks(read(RA/'rules/naval-systems.yaml'))}
 lines=f'''World:
\tFaction@{faction}:
\t\tName: faction-{faction}.name
\t\tInternalName: {faction}
\t\tSide: {'Allies' if allied else 'Soviet'}
\t\tDescription: faction-{faction}.description
\t\tRandomFactionMemberOf: {'RandomAllies' if allied else 'RandomSoviet'}
'''
 ownids=[b[2:].upper() for _,b,*_ in units]
 for mode in ('none','light','heavy'):
  support='' if mode=='none' else f'\t\tSupportActors: {ownids[0].lower()}, {ownids[0].lower()}, {ownids[1].lower()}'+(f', {ownids[4].lower()}, {ownids[5].lower()}' if mode=='heavy' else '')+'\n\t\tInnerSupportRadius: 3\n\t\tOuterSupportRadius: 5\n'
  lines+=f'\tStartingUnits@{faction}-{mode}:\n\t\tClass: {mode}\n\t\tClassName: options-starting-units.{"mcv-only" if mode=="none" else mode+"-support"}\n\t\tFactions: {faction}\n\t\tBaseActor: mcv\n'+support
 lines+=f'\nPlayer:\n\tProvidesFactionDoctrine@{prefix}:\n\t\tFactions: {faction}\n\t\tPrerequisites: side.{side}, country.{faction}, doctrine.{"precision-support" if allied else "concealed-defense"}\n\tCapturedTechnologyManager@{prefix}:\n\t\tFactions: {faction}\n'
 for bot in ('easy','medium','rush','normal','turtle','naval'):
  lines+=f'\tUnitBuilderBotModule@{bot}:\n\t\tUnitsToBuild:\n'
  for (_,actor,_,_,role,_) in units[:13 if allied else 12]: lines+=f'\t\t\t{actor[2:]}: {45 if role=="line-infantry" else 20 if role=="main-battle-tank" else 8}\n'
  lines+='\t\tUnitLimits:\n'+f'\t\t\t{ownids[3].lower()}: 1\n'
 for actor,tech in [('FACT','structures'),('WEAP','vehicles'),('TENT' if allied else 'BARR','infantry'),('HPAD' if allied else 'AFLD','aircraft'),('SYRD' if allied else 'SPEN','ships')]:
  lines+=f'\n{actor}:\n\tProvidesPrerequisite@{faction}:\n\t\tFactions: {faction}\n\t\tPrerequisite: {tech}.{faction}\n\tProvidesPrerequisite@{faction}-side:\n\t\tFactions: {faction}\n\t\tPrerequisite: {tech}.{side}\n'
 # Allied fixed-wing production has its own aircraft service building.
 if allied:
  lines+=f'\nILAIRFIELD:\n\tInherits: SAFLD\n\tBuildable:\n\t\tPrerequisites: dome, ~structures.israel, ~techlevel.medium\n\tProvidesPrerequisite@saudi:\n\t\tFactions: israel\n\t\tPrerequisite: aircraft.israel\n\tRenderSprites:\n\t\tImage: afld\n'
  lines+='\nPlayer:\n'  # merge nested base-builder fields without disturbing existing profiles
  for bot in ('normal','medium','rush','turtle','naval'):
   lines+=f'\tBaseBuilderBotModule@{bot}:\n\t\tAdditionalTechTypes:\n\t\t\tlevant: ilairfield, dome, fix, hpad, atek, stek\n\t\tAdditionalProductionTypes:\n\t\t\tlevant: ilairfield, hpad, afld, barr, tent, weap\n\t\tBuildingLimits:\n\t\t\tilairfield: 3\n\t\tBuildingFractions:\n\t\t\tilairfield: 1\n'
 for i,(src,actor,base,name,role,description) in enumerate(units):
  new=actor[2:].upper(); tech='infantry' if i<4 else 'vehicles' if i<8 else 'aircraft' if (allied and i<10 or not allied and i<9) else 'ships' if (allied and i<13 or not allied and i<12) else 'structures'
  inherited=base
  # Every actor has direct name and description for catalog/source validation.
  lines+=f'\n{new}:\n\tInherits: {inherited}\n\tTooltip:\n\t\tName: levant-{new.lower()}-name\n\tBuildable:\n\t\tPrerequisites: ~{tech}.{faction}'+(', dome' if role in ('artillery','anti-air','support','interceptor','strike-aircraft') else '')+f', ~techlevel.medium\n\t\tDescription: levant-{new.lower()}-description\n\tRenderSprites:\n\t\tImage: {new.lower()}\n\tVoiced:\n\t\tVoiceSet: {"GenericVoice" if i<4 else "VehicleVoice"}\n'
  if new=='ILFALCON': lines+='\tRearmable:\n\t\tRearmActors: ilairfield\n'
  if new=='ILRECON':
   lines+='\tAirstrikePower@PRECISION:\n\t\tOrderName: IsraelPrecisionStrike\n\t\tUnitType: ilstrike\n'
  if tech=='vehicles':
   lines+=f'\tExternalCondition@repair:\n\t\tCondition: {faction}-repair\n\tChangesHealth@field:\n\t\tStep: 200\n\t\tDelay: 25\n\t\tStartIfBelow: 70\n\t\tRequiresCondition: {faction}-repair\n'
   if allied: lines+='\tInherits@coordination: ^LevantIsraelCoordination\n'
  if allied and i<4: lines+='\tInherits@coordination: ^LevantIsraelCoordination\n'
  if new=='MERKAVA': lines+='\tValued:\n\t\tCost: 1450\n\tHealth:\n\t\tHP: 64000\n'
  if new=='NAMER': lines+='\tValued:\n\t\tCost: 1050\n\tHealth:\n\t\tHP: 42000\n\tCargo:\n\t\tMaxWeight: 5\n\t- AttackFrontal:\n\tTurreted:\n\t\tTurnSpeed: 28\n\tWithSpriteTurret:\n\tArmament:\n\t\tWeapon: RedSeaApacheCannon\n\tArmament@secondary:\n\t\tName: secondary\n\t\tWeapon: RedSeaATGM\n\tAttackTurreted:\n\t\tArmaments: primary, secondary\n'.replace('- AttackFrontal','-AttackFrontal')
  if new=='HZROCKETS': lines+='\tGrantConditionOnMovement@setup:\n\t\tCondition: moving\n\tReloadDelayMultiplier@setup:\n\t\tModifier: 70\n\t\tRequiresCondition: !moving\n'
  if new=='HZRECOILLESS': lines+='\tArmament:\n\t\tWeapon: RedSeaRPG\n'
  if new=='HZESCORT': lines+='\tArmament@primary:\n\t\tWeapon: RedSeaInterceptor\n'
  if tech=='structures':
   lines+='\tBuildable:\n\t\tPrerequisites: ~structures.'+faction+', dome, ~techlevel.medium\n'
   if new in ('ILBATTERY','HZAANEST'): pass
   elif new in ('ILATPOST','HZCOASTAL'): lines+='\tArmament:\n\t\tWeapon: RedSeaATGM\n'
   if new in ('HZBUNKER','HZCOASTAL'):
    lines+='\tCloak:\n\t\tInitialDelay: 75\n\t\tCloakDelay: 125\n\t\tUncloakOn: Attack, Damage\n\t\tCloakTypes: Cloak\n'
  if new=='HZMISSILEBOAT': lines+='\t-WithSpriteTurret:\n'
  if new=='ILHOWITZER': lines+='\tArmament:\n\t\tWeapon: 155mm\n'
  rolebase={'line-infantry':'RifleInfantry','anti-armor':'AntiArmorInfantry','support':'Engineer','main-battle-tank':'MainBattleTank','anti-air':'AntiAirVehicle','artillery':'Artillery','transport':'Transport','interceptor':'Interceptor','strike-aircraft':'AttackAircraft','naval-screen':'PatrolCraft','anti-submarine':'Destroyer'}.get(role,'Engineer')
  # Reusable role traits are metadata, independent of inherited body mechanics.
  lines+=f'\tInherits@WW3ROLE: {"^ReusableDefenseStructure" if tech=="structures" else "^Role"+rolebase}\n'
  if i<4: lines+='\tVoiced:\n\t\tVoiceSet: LevantClassicInfantryVoice\n'
  if tech=='structures' and base!='HBOX':lines+='\t-WithBuildingBib:\n'
 for actor,base in [('ILFALCON','F15SA'),('ILGUNSHIP','AH64SA')] if allied else [('HZDRONE','SAMAD')]:
  lines+=f'\n{actor}:\n\tSpawnActorOnDeath:\n\t\tActor: {actor}.Husk\n\n{actor}.Husk:\n\tInherits: {base}.Husk\n\tTooltip:\n\t\tName: levant-{actor.lower()}-name\n\tRenderSprites:\n\t\tImage: {actor.lower()}\n\t\tPlayerPalette: {faction}player\n'
 if allied: lines+='\nILSTRIKE:\n\tInherits: F15SA.STRIKE\n\tRenderSprites:\n\t\tImage: ilfalcon\n'
 lines+='\n'+support_rules(faction,'classic')
 write(RA/f'rules/{faction}.yaml',normalized(lines))
 locale=f'faction-{faction} =\n    .name = {title}\n    .description = Fictional RTS faction: {"protected armor, guided fire and powered coordination" if allied else "light forces, concealment and guided support"}.\n'
 for _,actor,_,name,_,desc in units: locale+=f'\nlevant-{actor[2:]}-name = {name}\nlevant-{actor[2:]}-description = {CLASSIC_DESCRIPTIONS.get(actor[2:],desc)}\n'
 for suffix,label,desc in [('relay','Coordination Relay' if allied else 'Signal Post','Powered six-cell support aura and five-cell cloak detection. Losing power disables the benefits. Bonuses do not stack.'),('workshop','Field Service Station' if allied else 'Field Workshop','Powered four-cell repair zone. Eligible vehicles repair 200 health per second below 70% health. Does not stack; unarmed and vulnerable.')]: locale+=f'\nlevant-{prefix.lower()+suffix}-name = {label}\nlevant-{prefix.lower()+suffix}-description = {desc}\n'
 write(RA/f'fluent/{faction}.ftl',locale)
 seq=''
 sequence_sources={**blocks(read(RA/'sequences/red-sea.yaml')),**blocks(read(RA/'sequences/naval-systems.yaml')),**blocks(read(RA/'sequences/vehicles.yaml')),**blocks(read(RA/'sequences/structures.yaml'))}
 for _,actor,base,*_ in units:
  new=actor[2:]; image=base.lower(); inherited=sequence_sources.get(image)
  seq+=f'{new}:\n\tInherits: {image}\n\n'
 # support structures use purpose-built owned art in the following asset pass.
 for suffix in ('relay','workshop'): seq+=f'{prefix.lower()+suffix}:\n\tInherits: pbox\n\n'
 write(RA/f'sequences/{faction}.yaml',seq)
 path=RA/'experiences.yaml'; text=read(path)
 entry=f'''\t\t{faction}-faction:
\t\t\tTitle: {title}
\t\t\tDescription: Fictional RTS faction; {"precision armor and protected support" if allied else "light forces and concealed defense"}.
\t\t\tEffects: Complete faction roster, production trees, support buildings and bot composition.
\t\t\tTradeoffs: {"High costs and dependency on vulnerable support" if allied else "Low durability and dependency on detection gaps"}.
\t\t\tScope: Selectable faction; local development content.
\t\t\tCategory: Faction packs
\t\t\tVersion: 1
\t\t\tSource: Original project rules and procedural art
\t\t\tLicense: GPL-3.0-or-later code; original project presentation
\t\t\tKind: Faction
\t\t\tDependencies: faction-and-subfaction-contract, red-sea-roster-content, naval-combat-archetypes
\t\t\tRules: ra|rules/levant-common.yaml, ra|rules/{faction}.yaml
\t\t\tSequences: ra|sequences/{faction}.yaml
\t\t\tFaction:
\t\t\t\tInternalName: {faction}
\t\t\t\tSide: {'Allies' if allied else 'Soviet'}
\t\t\t\tRandomPool: {'RandomAllies' if allied else 'RandomSoviet'}
\t\t\t\tDoctrine: {'precision-support' if allied else 'concealed-defense'}
\t\t\t\tPreview: ra|uibits/faction-previews/{faction}.png
\t\t\t\tRoster:
\t\t\t\t\tInfantry: {', '.join(ownids[:4])}
\t\t\t\t\tVehicles: {', '.join(ownids[4:8])}
\t\t\t\t\tAircraft: {', '.join(ownids[8:10 if allied else 9])}
\t\t\t\t\tNavy: {', '.join(ownids[10 if allied else 9:13 if allied else 12])}
\t\t\t\t\tBuildings: FACT, WEAP, {'TENT, HPAD, ILAIRFIELD, SYRD' if allied else 'BARR, AFLD, SPEN'}, {prefix}RELAY, {prefix}WORKSHOP
\t\t\t\t\tDefenses: {', '.join(ownids[-3:])}
'''
 if f'\t\t{faction}-faction:' in text:
  text=re.sub(r'^\t\t'+faction+r'-faction:\n.*?(?=^\t\t[^\t\n]|\Z)',lambda _:entry,text,flags=re.S|re.M)
 else:
  text=text.replace('\t\tsaudi-arabia-faction:',entry+'\t\tsaudi-arabia-faction:')
  text=text.replace('Components: saudi-arabia-faction,','Components: '+faction+'-faction, saudi-arabia-faction,') if faction=='israel' else text.replace('Components: israel-faction,','Components: hezbollah-faction, israel-faction,')
 write(path,text)
 # Fluent is global; loading it does not enable the faction outside its profile.
 add_manifest(RA/'mod.yaml','FluentMessages:',f'\tra|fluent/{faction}.ftl')

def main():
 for faction,(source,_,_,_) in FACTIONS.items():
  build_ra2(faction,source,FACTIONS[faction][1]); classic(faction,source,FACTIONS[faction][1])
 common='''^LevantIsraelCoordination:
\tExternalCondition@coordination:
\t\tCondition: israel-linked
\tReloadDelayMultiplier@coordination:
\t\tModifier: 85
\t\tRequiresCondition: israel-linked
\tWithTextDecoration@coordination:
\t\tText: LINK
\t\tColor: 80B8FF
\t\tRequiresCondition: israel-linked
\t\tRequiresSelection: true
'''
 common+='\nPlayer:\n'
 for faction in FACTIONS: common+=f'\tProvidesPrerequisite@{faction}:\n\t\tPrerequisite: faction.{faction}\n\t\tFactions: {faction}\n'
 write(PACK/'levant-common.yaml',common); write(RA/'rules/levant-common.yaml',common)
 add_manifest(MOD/'mod.yaml','\tra2|modern-factions/common.yaml','\tra2|modern-factions/levant-common.yaml')
 world=read(MOD/'rules/world.yaml').replace('korea, china, turkey, saudi','korea, china, turkey, saudi, israel').replace('russia, iran, yemen','russia, iran, yemen, hezbollah');write(MOD/'rules/world.yaml',world)
 metrics=read(MOD/'metrics.yaml');
 if 'FactionSuffix-israel:' not in metrics: metrics=metrics.replace('FactionSuffix-saudi: allies','FactionSuffix-israel: allies\n\tFactionSuffix-hezbollah: soviets\n\tFactionSuffix-saudi: allies')
 write(MOD/'metrics.yaml',metrics)
 replacements=read(PACK/'shared-replacements.yaml').replace('~!faction.saudi','~!faction.saudi, ~!faction.israel').replace('~!faction.yemen','~!faction.yemen, ~!faction.hezbollah');write(PACK/'shared-replacements.yaml',replacements)
 doctrines=read(PACK/'doctrines.yaml')
 if 'BotDoctrine@israel:' not in doctrines:
  doctrines+='''\n\tBotDoctrine@israel:
\t\tFactions: israel
\t\tDoctrine: precision-support
\t\tAirDefenseShare: 24
\t\tInitialBuildOrder: gapowr, garefn, gapile, gaweap, garefn, gaairc, r2ilrelay
\t\tSquadSizeModifier: 75
\t\tRoleShareModifiers:
\t\t\tmain-battle-tank: 135
\t\t\tsupport: 140
\t\t\ttransport: 120
\t\t\tanti-air: 40
\tBotDoctrine@hezbollah:
\t\tFactions: hezbollah
\t\tDoctrine: concealed-defense
\t\tAirDefenseShare: 24
\t\tInitialBuildOrder: napowr, nahand, narefn, r2hzbunker, naweap, narefn, naradr, r2hzrelay
\t\tSquadSizeModifier: 130
\t\tRoleShareModifiers:
\t\t\tline-infantry: 140
\t\t\tanti-armor: 140
\t\t\tartillery: 125
\t\t\tsupport: 120
\t\t\tanti-air: 40
'''
 write(PACK/'doctrines.yaml',doctrines)
 # Dedicated neutral voice adapters supply every requested native action.
 write(PACK/'levant-voices.yaml','''LevantInfantryVoice:
\tInherits: GIVoice
\tVoices:
\t\tDemolish: igiata
\t\tBuild: igisea
\t\tAction: igimoa
LevantVehicleVoice:
\tInherits: AlliedVehicleVoice
\tVoices:
\t\tDie: vgrasea
\t\tAction: vgrasea
''')
 add_manifest(MOD/'mod.yaml','Voices:','\tra2|modern-factions/levant-voices.yaml')
 for filename,anchor,new in [('voice-prefixes.yaml','\tPrefixes:','\t\tisrael: iena\n\t\thezbollah: iens'),('eva-notifications.yaml','\tPrefixes:','\t\tisrael: ceva\n\t\thezbollah: csof')]:add_manifest(PACK/filename,anchor,new)
 # Classic adapters keep the original side voices and expose the specialist actions.
 voice=read(RA/'audio/voices.yaml')
 for faction,side in [('israel','allies'),('hezbollah','soviet')]:
  for key,variants in [('GenericVoice','.v01,.v03' if side=='allies' else '.r01,.r03'),('VehicleVoice','.v00,.v02' if side=='allies' else '.r00,.r02')]:
   block=blocks(voice).get(key,'')
   if f'\t\t{faction}:' not in block:voice=voice.replace(block,block.replace('\tVariants:',f'\tVariants:\n\t\t{faction}: {variants}'))
 write(RA/'audio/voices.yaml',voice)
 if 'LevantClassicInfantryVoice:' not in voice:
  write(RA/'audio/voices.yaml',voice+'''\nLevantClassicInfantryVoice:
\tInherits: GenericVoice
\tVoices:
\t\tMove: ackno
\t\tDemolish: ackno
\t\tBuild: ready
\t\tKill: ackno
''')
 cursors=read(RA/'cursors.yaml')
 if '\tisrael:\n' not in cursors:
  cursors+='''\n\tisrael:
\t\tPrimaryColor: 80B8FF
\t\tSecondaryColor: E4EAD8
\t\tStyle: Cross
\thezbollah:
\t\tPrimaryColor: B3B881
\t\tSecondaryColor: E1DBB9
\t\tStyle: Streaks
'''
 write(RA/'cursors.yaml',cursors)
 # Normalize generated comma lists so repeated builds remain idempotent.
 for path in [MOD/'rules/world.yaml',PACK/'shared-replacements.yaml']:
  text=read(path);text=re.sub(r'^(\s*(?:RandomFactionMembers|Prerequisites): )(.*)$',lambda m:m[1]+', '.join(dict.fromkeys(x.strip() for x in m[2].split(','))),text,flags=re.M);write(path,text)
 print(json.dumps({'israelExclusiveActors':18,'hezbollahExclusiveActors':17,'modes':['ra','ra2'],'paidSpend':0}))

if __name__=='__main__': main()
