local Config = __CONFIG__
local A, B, actors, repaired, unassisted, workshop, cloak, aircraft, hostileAir
local power = {}
local produced = {}
local finished = false
local powerOffTick=nil
local initialLocations={}
local function Cell(x,y)
  if Config.ra2 then return CPos.New(x+34,y-30) end
  return CPos.New(x,y)
end
local function Check(label, ok, detail)
  print('CHECK|'..(ok and 'PASS' or 'FAIL')..'|'..label..'|'..tostring(detail or ''))
end
local function Spawn(owner, typ, x,y)
  local a=Actor.Create(typ,true,{Owner=owner,Location=Cell(x,y),Facing=Angle.North})
  if a.HasProperty('Stance') then a.Stance='HoldFire' end
  return a
end
WorldLoaded=function()
  A=Player.GetPlayer('DuelA'); B=Player.GetPlayer('DuelB')
  actors={}
  for i,typ in ipairs(Config.israel) do actors[#actors+1]=Spawn(A,typ,8+(i-1)%5*5,8+math.floor((i-1)/5)*5) end
  for i,typ in ipairs(Config.hezbollah) do actors[#actors+1]=Spawn(B,typ,36+(i-1)%5*5,8+math.floor((i-1)/5)*5) end
  Check('roster-instantiation',#actors==#Config.israel+#Config.hezbollah,#actors)
  if Config.naval then
    Spawn(B,Config.ra2 and 'nayard' or 'spen',39,11)
    for i,a in ipairs(actors) do initialLocations[a]=a.Location end
    if not Config.ra2 then actors[5].GrantCondition('remote-link') end
    for i,a in ipairs(actors) do a.Move(Cell(i<4 and 12+i*3 or 42+(i-3)*3,28)) end
    return
  end
  local aTypes=Config.ra2 and {'gacnst','gapowr','gapowr','gapowr','gapowr','gapowr','gapowr','gapowr','garefn','gapile','gaweap','gaairc','gatech'} or {'fact','powr','powr','powr','powr','powr','powr','powr','proc','tent','weap','dome','atek','ilairfield','hpad'}
  local bTypes=Config.ra2 and {'nacnst','napowr','napowr','napowr','napowr','napowr','napowr','napowr','narefn','nahand','naweap','naradr','natech'} or {'fact','powr','powr','powr','powr','powr','powr','powr','proc','barr','weap','dome','stek','afld'}
  for i,typ in ipairs(aTypes) do local a=Spawn(A,typ,(typ=='gaweap' or typ=='weap') and 12 or 6+(i-1)%5*5,(typ=='gaweap' or typ=='weap') and 44 or 30+math.floor((i-1)/5)*5); if string.find(typ,'pow') then power[#power+1]=a end end
  for i,typ in ipairs(bTypes) do Spawn(B,typ,(typ=='naweap' or typ=='weap') and 40 or 36+(i-1)%5*5,(typ=='naweap' or typ=='weap') and 44 or 30+math.floor((i-1)/5)*5) end
  A.Cash=100000; B.Cash=100000
  repaired=Spawn(A,Config.ra2 and 'r2merkava' or 'merkava',12,52)
  unassisted=Spawn(A,Config.ra2 and 'r2merkava' or 'merkava',24,52)
  repaired.Health=math.floor(repaired.MaxHealth*.4);unassisted.Health=math.floor(unassisted.MaxHealth*.4)
  workshop=Spawn(A,Config.ra2 and 'r2ilworkshop' or 'ilworkshop',10,52)
  cloak=Spawn(B,Config.ra2 and 'r2hzrifle' or 'hzrifle',50,52)
  aircraft=Spawn(A,Config.ra2 and 'r2ilfalcon' or 'ilfalcon',27,50)
  aircraft.Move(Cell(28,52))
  hostileAir=Spawn(B,Config.ra2 and 'r2hzdrone' or 'hzdrone',32,52)
  hostileAir.Move(Cell(33,53))
end
Tick=function()
  if finished then return end
  local t=DateTime.GameTime
  if Config.naval then
    if t==500 then
      for i,a in ipairs(actors) do Check('naval-movement-'..a.Type,a.Location~=initialLocations[a],a.Location) end
      print('CHECK|DONE');finished=true
    end
    return
  end
  if t==10 then
    Check('israel-production-prerequisites',A.HasPrerequisites(Config.ra2 and {'faction.israel','gaweap'} or {'vehicles.israel','infantry.israel'}))
    Check('hezbollah-production-prerequisites',B.HasPrerequisites(Config.ra2 and {'faction.hezbollah','naweap'} or {'vehicles.hezbollah','infantry.hezbollah'}))
    A.Build({Config.ra2 and 'r2ilrifle' or 'ilrifle'},function(g) produced.ilinf=#g end)
    A.Build({Config.ra2 and 'r2merkava' or 'merkava'},function(g) produced.ilvehicle=#g end)
    A.Build({Config.ra2 and 'r2ilfalcon' or 'ilfalcon'},function(g) produced.ilair=#g end)
    B.Build({Config.ra2 and 'r2hzrifle' or 'hzrifle'},function(g) produced.hzinf=#g end)
    Check('off-faction-prerequisites-rejected',not A.HasPrerequisites({'faction.hezbollah'}) and not B.HasPrerequisites({'faction.israel'}))
    Check('hezbollah-vehicle-air-queue-start',B.Build({Config.ra2 and 'r2hztechnical' or 'hztechnical',Config.ra2 and 'r2hzdrone' or 'hzdrone'},function(g)
      for _,a in ipairs(g) do if a.Type==(Config.ra2 and 'r2hztechnical' or 'hztechnical') then produced.hzvehicle=1 else produced.hzair=1 end end
    end))
  end
  if t==170 then aircraft.Move(Cell(25,8)) end
  if t==200 then
    Check('stationary-concealment',cloak.IsCloaked)
    Check('repair-aura-eligible-only',repaired.Health>unassisted.Health,repaired.Health..'/'..unassisted.Health)
    local aa=Spawn(A,Config.ra2 and 'r2ilshield' or 'ilshield',28,52)
    Check('air-defense-rejects-ground',not aa.CanTarget(cloak))
    Check('air-defense-accepts-air',aa.CanTarget(hostileAir))
    aircraft.Kill()
  end
  if t==201 then
    Check('aircraft-falling-husk',#A.GetActorsByType(Config.ra2 and 'r2ilfalconhusk' or 'ilfalcon.husk')==1)
    cloak.Move(Cell(51,54))
  end
  if t==215 then Check('movement-breaks-concealment',not cloak.IsCloaked) end
  if not powerOffTick and produced.ilinf and produced.ilvehicle and produced.ilair and produced.hzinf and produced.hzvehicle and produced.hzair then
    for _,a in ipairs(power) do a.Destroy() end
    repaired.Health=math.floor(repaired.MaxHealth*.4);unassisted.Health=math.floor(unassisted.MaxHealth*.4)
    powerOffTick=t
  end
  if powerOffTick and t==powerOffTick+125 then Check('repair-disabled-without-power',repaired.Health==unassisted.Health,repaired.Health..'/'..unassisted.Health) end
  if (powerOffTick and t==powerOffTick+150) or t==4000 then
    for _,k in ipairs({'ilinf','ilvehicle','ilair','hzinf','hzvehicle','hzair'}) do Check('queue-produces-'..k,(produced[k] or 0)>0,produced[k]) end
    print('CHECK|DONE');finished=true
  end
end
