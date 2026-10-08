--[[
Bot-vs-bot balance telemetry, installed into a disposable copy of a map by
scripts/balance_harness.py. It only observes: it never issues orders, grants
resources or changes either army. The one intervention is the harness tick
cap, which fails both players' objectives at the same tick so the match ends
as a recorded draw and the engine writes a complete replay.

Output: one "BALANCE|<match>|<event>|<tick>|..." line per event in lua.log.
]]

local MatchId = "__MATCH_ID__"
local SampleInterval = __SAMPLE_INTERVAL__
local TickCap = __TICK_CAP__

local Combatants = { }
local Stats = { }
local CostCache = { }
local Tracked = { }

local function Emit(kind, fields)
	local parts = { "BALANCE", MatchId, kind, tostring(DateTime.GameTime) }
	for i = 1, #fields do
		parts[#parts + 1] = tostring(fields[i])
	end
	print(table.concat(parts, "|"))
end

local function CostOf(actorType)
	local cached = CostCache[actorType]
	if cached == nil then
		local ok, value = pcall(function() return Actor.Cost(actorType) end)
		cached = ok and value or 0
		CostCache[actorType] = cached
	end
	return cached
end

local function Role(queue)
	if queue == nil or queue == "" then
		return "Other"
	end
	return queue
end

local function IsBuilding(actor)
	return actor.HasProperty("StartBuildingRepairs")
end

-- Lua may wrap one actor in several userdata values; key by actor ID.
local function ActorKey(actor)
	return string.match(tostring(actor), "^Actor %(%S+ (%d+)")
end

-- Records the actor's death (with the role it was produced under) once.
local function Track(actor, role)
	local key = ActorKey(actor)
	if key == nil or Tracked[key] then
		return
	end

	Tracked[key] = true
	local ownerName = actor.Owner.InternalName
	local actorType = actor.Type
	local cost = CostOf(actorType)
	Trigger.OnKilled(actor, function(self, killer)
		local killerName = "none"
		if killer ~= nil and killer.Owner ~= nil then
			killerName = killer.Owner.InternalName
		end

		Emit("lost", { ownerName, actorType, role, cost, killerName })
	end)
end

local function Sample()
	for _, player in ipairs(Combatants) do
		local stats = Stats[player.InternalName]
		-- Army: living armed non-building actors, valued at their build cost.
		local army, armed = 0, 0
		local actors = player.GetActors()
		for _, actor in ipairs(actors) do
			if IsBuilding(actor) then
				-- Construction yards from deployed MCVs and captured buildings.
				Track(actor, "Building")
			elseif actor.HasProperty("Attack") then
				army = army + CostOf(actor.Type)
				armed = armed + 1
			end
		end

		Emit("sample", {
			player.InternalName, player.Cash, player.Resources,
			player.KillsCost, player.DeathsCost,
			player.UnitsKilled, player.UnitsLost,
			player.BuildingsKilled, player.BuildingsLost,
			army, armed, stats.unitSpend, stats.buildingSpend,
			#actors
		})
	end
end

local function SampleLoop()
	Sample()
	if DateTime.GameTime >= TickCap then
		Emit("cap", { TickCap })
		-- Resolve both players in the same tick: a draw, not a win for either.
		for _, player in ipairs(Combatants) do
			local objective = player.AddPrimaryObjective("Balance harness tick cap")
			player.MarkFailedObjective(objective)
		end
		return
	end

	Trigger.AfterDelay(SampleInterval, SampleLoop)
end

WorldLoaded = function()
	Combatants = Player.GetPlayers(function(player)
		return not player.IsNonCombatant and string.sub(player.InternalName, 1, 5) == "Multi"
	end)

	for _, player in ipairs(Combatants) do
		Stats[player.InternalName] = { unitSpend = 0, buildingSpend = 0 }
		Emit("player", { player.InternalName, player.Faction, player.Spawn, tostring(player.IsBot) })

		-- A closing sample records the final kills/losses at the deciding tick.
		Trigger.OnPlayerWon(player, function(p) Emit("won", { p.InternalName }) Sample() end)
		Trigger.OnPlayerLost(player, function(p) Emit("defeated", { p.InternalName }) Sample() end)
		Trigger.OnBuildingPlaced(player, function(p, placed)
			local stats = Stats[p.InternalName]
			local cost = CostOf(placed.Type)
			stats.buildingSpend = stats.buildingSpend + cost
			Emit("placed", { p.InternalName, placed.Type, cost })
			Track(placed, "Building")
		end)
	end

	Trigger.OnAnyProduction(function(producer, produced, productionType)
		local owner = produced.Owner
		local stats = Stats[owner.InternalName]
		if stats == nil then
			return
		end

		local role = Role(productionType)
		local cost = CostOf(produced.Type)
		stats.unitSpend = stats.unitSpend + cost
		Emit("produced", { owner.InternalName, produced.Type, role, cost })
		Track(produced, role)
	end)

	-- Starting units and pre-placed structures (MCV, starting armies).
	Trigger.AfterDelay(1, function()
		for _, player in ipairs(Combatants) do
			for _, actor in ipairs(player.GetActors()) do
				if IsBuilding(actor) then
					Track(actor, "Building")
				elseif actor.HasProperty("Move") or actor.HasProperty("Deploy") then
					Emit("starting", { player.InternalName, actor.Type, CostOf(actor.Type) })
					Track(actor, "Starting")
				end
			end
		end

		Trigger.AfterDelay(SampleInterval - 1, SampleLoop)
	end)
end
