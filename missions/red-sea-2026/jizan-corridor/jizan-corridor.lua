--[[
   Copyright (c) The OpenRA Developers and Contributors
   This file is part of OpenRA, which is free software. It is made
   available to you under the terms of the GNU General Public License
   as published by the Free Software Foundation, either version 3 of
   the License, or (at your option) any later version. For more
   information, see COPYING.
]]

ConvoyPath = { ConvoyRally.Location, CorridorOne.Location, CorridorTwo.Location,
	CorridorThree.Location, PortGate.Location, ConvoyExit.Location }

DifficultySettings = {
	easy = { RequiredTrucks = 2, DroneCount = 2, AmbushSize = 4, ReinforcementDelay = DateTime.Seconds(24) },
	normal = { RequiredTrucks = 2, DroneCount = 3, AmbushSize = 6, ReinforcementDelay = DateTime.Seconds(18) },
	hard = { RequiredTrucks = 3, DroneCount = 4, AmbushSize = 8, ReinforcementDelay = DateTime.Seconds(12) }
}

RadarCaptured = false
LaunchersDestroyed = false
ConvoyStarted = false
ConvoyEscaped = 0
ConvoyLost = 0
InfrastructureLost = false

PlayRadio = function(file, message, speaker)
	Media.PlaySound(file)
	Media.DisplayMessage(UserInterface.GetFluentMessage(message), UserInterface.GetFluentMessage(speaker))
end

HuntOnIdle = function(actor)
	if actor and not actor.IsDead then
		Trigger.OnIdle(actor, actor.Hunt)
	end
end

GuardLauncher = function(actor, launcher)
	if actor and not actor.IsDead and launcher and not launcher.IsDead then
		actor.Guard(launcher)
	end
end

SendGroundWave = function(entry, rally, amount)
	local types = { "tech", "tech", "e1", "e2" }
	for i = 1, amount do
		local unit = Actor.Create(types[((i - 1) % #types) + 1], true,
			{ Owner = Yemen, Location = entry.Location + CVec.New(i % 3, math.floor(i / 3)) })
		unit.AttackMove(rally.Location)
		HuntOnIdle(unit)
	end
end

SendDroneWave = function()
	PlayRadio("redsea-jizan-drone-warning-en.wav", "radio-drone-warning-en", "air-defense-net")
	for i = 1, Settings.DroneCount do
		local entry = i % 2 == 0 and DroneEntryNorth or DroneEntrySouth
		local drone = Actor.Create("samad", true, { Owner = Yemen, Location = entry.Location })
		if i % 2 == 0 and not PortDepot.IsDead then
			drone.Attack(PortDepot)
		elseif not RadarNode.IsDead then
			drone.Attack(RadarNode)
		end
		HuntOnIdle(drone)
	end
end

RevealLaunchers = function()
	local westCamera = Actor.Create("camera", true, { Owner = Saudi, Location = LauncherWestCamera.Location })
	local eastCamera = Actor.Create("camera", true, { Owner = Saudi, Location = LauncherEastCamera.Location })
	Trigger.AfterDelay(DateTime.Seconds(10), function()
		if not westCamera.IsDead then westCamera.Destroy() end
		if not eastCamera.IsDead then eastCamera.Destroy() end
	end)
	PlayRadio("redsea-jizan-launchers-ar.wav", "radio-launchers-ar", "saudi-command")
end

TryStartConvoy = function()
	if ConvoyStarted or not RadarCaptured or not LaunchersDestroyed then
		return
	end

	ConvoyStarted = true
	Saudi.MarkCompletedObjective(DestroyLaunchersObjective)
	PlayRadio("redsea-jizan-convoy-ar.wav", "radio-convoy-ar", "saudi-command")
	Trigger.AfterDelay(DateTime.Seconds(3), StartConvoy)
	Trigger.AfterDelay(DateTime.Seconds(10), function() SendGroundWave(WestEntry, CorridorOne, Settings.AmbushSize) end)
	Trigger.AfterDelay(DateTime.Seconds(28), function() SendGroundWave(EastEntry, CorridorThree, Settings.AmbushSize) end)
end

AdvanceTruck = function(truck)
	local step = 1
	local advance = nil
	advance = function()
		if truck.IsDead or step > #ConvoyPath then
			return
		end
		local destination = ConvoyPath[step]
		step = step + 1
		truck.Move(destination)
	end
	Trigger.OnIdle(truck, advance)
	advance()
end

ConvoyTruckLost = function()
	ConvoyLost = ConvoyLost + 1
	PlayRadio("redsea-jizan-convoy-loss-en.wav", "radio-convoy-loss-en", "jizan-control")
	if 3 - ConvoyLost < Settings.RequiredTrucks and not Saudi.IsObjectiveFailed(EscortConvoyObjective) then
		Saudi.MarkFailedObjective(EscortConvoyObjective)
	end
end

StartConvoy = function()
	local trucks = { }
	for i = 0, 2 do
		local truck = Actor.Create("truk", true, { Owner = Civilians, Location = ConvoyEntry.Location + CVec.New(i, i) })
		trucks[#trucks + 1] = truck
		Trigger.OnKilled(truck, ConvoyTruckLost)
		AdvanceTruck(truck)
	end

	Trigger.OnEnteredFootprint({ ConvoyExit.Location }, function(actor, id)
		if actor.Owner ~= Civilians or actor.Type ~= "truk" then
			return
		end

		ConvoyEscaped = ConvoyEscaped + 1
		actor.Destroy()
		UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-convoy",
			{ ["escaped"] = ConvoyEscaped, ["required"] = Settings.RequiredTrucks }), Saudi.Color)
		if ConvoyEscaped >= Settings.RequiredTrucks then
			Trigger.RemoveFootprintTrigger(id)
			UserInterface.SetMissionText("")
			PlayRadio("redsea-jizan-secure-en.wav", "radio-corridor-secure-en", "jizan-control")
			Saudi.MarkCompletedObjective(EscortConvoyObjective)
			if not InfrastructureLost then
				Saudi.MarkCompletedObjective(ProtectInfrastructureObjective)
			end
		end
	end)
end

CriticalInfrastructureLost = function()
	if InfrastructureLost then
		return
	end
	InfrastructureLost = true
	PlayRadio("redsea-jizan-infrastructure-lost-en.wav", "radio-infrastructure-lost-en", "jizan-control")
	Saudi.MarkFailedObjective(ProtectInfrastructureObjective)
end

WorldLoaded = function()
	Saudi = Player.GetPlayer("Saudi Arabia")
	Yemen = Player.GetPlayer("Yemen")
	Civilians = Player.GetPlayer("Civilians")
	Settings = DifficultySettings[Map.LobbyOptionOrDefault("difficulty", "normal")]

	InitObjectives(Saudi)
	YemenObjective = AddPrimaryObjective(Yemen, "")
	RestoreRadarObjective = AddPrimaryObjective(Saudi, "restore-radar")
	DestroyLaunchersObjective = AddPrimaryObjective(Saudi, "destroy-mobile-launchers")
	EscortConvoyObjective = AddPrimaryObjective(Saudi, "escort-relief-convoy")
	ProtectInfrastructureObjective = AddSecondaryObjective(Saudi, "protect-critical-infrastructure")

	Trigger.OnCapture(RadarNode, function()
		if RadarCaptured then return end
		RadarCaptured = true
		Saudi.MarkCompletedObjective(RestoreRadarObjective)
		PlayRadio("redsea-jizan-radar-ar.wav", "radio-radar-ar", "saudi-command")
		RevealLaunchers()
		Trigger.AfterDelay(DateTime.Seconds(8), SendDroneWave)
		Trigger.AfterDelay(Settings.ReinforcementDelay,
			function() SendGroundWave(SouthEntry, SaudiEntry, Settings.AmbushSize) end)
		TryStartConvoy()
	end)

	Trigger.OnKilled(RadarNode, function()
		if not RadarCaptured then Saudi.MarkFailedObjective(RestoreRadarObjective) end
	end)
	Trigger.OnAllKilled({ LauncherWest, LauncherEast }, function()
		LaunchersDestroyed = true
		TryStartConvoy()
	end)
	Trigger.OnAnyKilled({ PortDepot, Desalination }, CriticalInfrastructureLost)

	-- Keep the opening readable: these units protect their launch sites instead
	-- of crossing the map and destroying the engineer/infrastructure before the
	-- player can act.  The post-capture waves still use HuntOnIdle.
	GuardLauncher(WestGuard1, LauncherWest)
	GuardLauncher(WestGuard2, LauncherWest)
	GuardLauncher(EastGuard1, LauncherEast)
	GuardLauncher(EastGuard2, LauncherEast)
	Camera.Position = SaudiEntry.CenterPosition
	-- The scripted world can initialize one frame before the interactive
	-- renderer. Recenter again after it is live so visible launches never open
	-- on the black area outside the playable map; headless runs safely no-op.
	Trigger.AfterDelay(DateTime.Seconds(1), function()
		Camera.Position = SaudiEntry.CenterPosition
	end)
	PlayRadio("redsea-jizan-opening-en.wav", "radio-opening-en", "jizan-control")
end

Tick = function()
	if Saudi.HasNoRequiredUnits() and not Saudi.IsObjectiveFailed(EscortConvoyObjective) then
		Saudi.MarkFailedObjective(EscortConvoyObjective)
		Yemen.MarkCompletedObjective(YemenObjective)
	end
end
