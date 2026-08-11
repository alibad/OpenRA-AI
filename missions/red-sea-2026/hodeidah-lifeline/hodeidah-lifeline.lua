--[[
   Copyright (c) The OpenRA Developers and Contributors
   This file is part of OpenRA, which is free software. It is made
   available to you under the terms of the GNU General Public License
   as published by the Free Software Foundation, either version 3 of
   the License, or (at your option) any later version. For more
   information, see COPYING.
]]

ReliefPath = { PortRally.Location, ReliefOne.Location, ReliefTwo.Location,
	ReliefThree.Location, DistributionGate.Location, ReliefExit.Location }
EvacuationPath = { DistributionGate.Location, ReliefThree.Location, ReliefTwo.Location,
	ReliefOne.Location, PortRally.Location, EvacExit.Location }

DifficultySettings = {
	easy = { RequiredTrucks = 2, WaveSize = 4, SweepDelay = 75, AllowedExposed = 2 },
	normal = { RequiredTrucks = 2, WaveSize = 6, SweepDelay = 60, AllowedExposed = 1 },
	hard = { RequiredTrucks = 3, WaveSize = 8, SweepDelay = 48, AllowedExposed = 0 }
}

ReliefDelivered = 0
ReliefLost = 0
EvacuationEscaped = 0
EvacuationLost = 0
ReliefComplete = false
DispersalComplete = false
EvacuationStarted = false
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

SendSaudiWave = function(entry, rally, amount)
	local types = { "e1", "e3", "m1a2s", "sads" }
	for i = 1, amount do
		local unit = Actor.Create(types[((i - 1) % #types) + 1], true,
			{ Owner = Saudi, Location = entry.Location + CVec.New(i % 3, math.floor(i / 3)) })
		unit.AttackMove(rally.Location)
		HuntOnIdle(unit)
	end
end

AdvanceTruck = function(truck, path)
	local step = 1
	local advance = nil
	advance = function()
		if truck.IsDead or step > #path then
			return
		end
		local destination = path[step]
		step = step + 1
		truck.Move(destination)
	end
	Trigger.OnIdle(truck, advance)
	advance()
end

ConvoyVehicleLost = function(stage)
	PlayRadio("redsea-hodeidah-convoy-loss-en.wav", "radio-hodeidah-convoy-loss-en", "hodeidah-control")
	if stage == "relief" then
		ReliefLost = ReliefLost + 1
		if 3 - ReliefLost < Settings.RequiredTrucks and not Yemen.IsObjectiveFailed(DeliverReliefObjective) then
			Yemen.MarkFailedObjective(DeliverReliefObjective)
		end
	else
		EvacuationLost = EvacuationLost + 1
		if 3 - EvacuationLost < Settings.RequiredTrucks and not Yemen.IsObjectiveFailed(EvacuationObjective) then
			Yemen.MarkFailedObjective(EvacuationObjective)
		end
	end
end

StartReliefConvoy = function()
	PlayRadio("redsea-hodeidah-relief-en.wav", "radio-hodeidah-relief-en", "hodeidah-control")
	for i = 0, 2 do
		local truck = Actor.Create("truk", true,
			{ Owner = Civilians, Location = PortEntry.Location + CVec.New(i, i) })
		Trigger.OnKilled(truck, function() ConvoyVehicleLost("relief") end)
		AdvanceTruck(truck, ReliefPath)
	end

	Trigger.OnEnteredFootprint({ ReliefExit.Location }, function(actor, id)
		if actor.Owner ~= Civilians or actor.Type ~= "truk" or ReliefComplete then
			return
		end
		ReliefDelivered = ReliefDelivered + 1
		actor.Destroy()
		UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-relief",
			{ ["delivered"] = ReliefDelivered, ["required"] = Settings.RequiredTrucks }), Yemen.Color)
		if ReliefDelivered >= Settings.RequiredTrucks then
			ReliefComplete = true
			Trigger.RemoveFootprintTrigger(id)
			UserInterface.SetMissionText("")
			Yemen.MarkCompletedObjective(DeliverReliefObjective)
			Trigger.AfterDelay(DateTime.Seconds(5), StartEvacuationConvoy)
			Trigger.AfterDelay(DateTime.Seconds(8),
				function() SendSaudiWave(EastEntry, ReliefThree, Settings.WaveSize) end)
		end
	end)
end

StartEvacuationConvoy = function()
	if EvacuationStarted then return end
	EvacuationStarted = true
	PlayRadio("redsea-hodeidah-evac-ar.wav", "radio-hodeidah-evac-ar", "yemen-coast-command")
	for i = 0, 2 do
		local truck = Actor.Create("truk", true,
			{ Owner = Civilians, Location = EvacEntry.Location + CVec.New(-i, i) })
		Trigger.OnKilled(truck, function() ConvoyVehicleLost("evacuation") end)
		AdvanceTruck(truck, EvacuationPath)
	end

	Trigger.OnEnteredFootprint({ EvacExit.Location }, function(actor, id)
		if actor.Owner ~= Civilians or actor.Type ~= "truk" then
			return
		end
		EvacuationEscaped = EvacuationEscaped + 1
		actor.Destroy()
		UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-evac",
			{ ["escaped"] = EvacuationEscaped, ["required"] = Settings.RequiredTrucks }), Yemen.Color)
		if EvacuationEscaped >= Settings.RequiredTrucks then
			Trigger.RemoveFootprintTrigger(id)
			UserInterface.SetMissionText("")
			Yemen.MarkCompletedObjective(EvacuationObjective)
			if not InfrastructureLost then
				Yemen.MarkCompletedObjective(ProtectInfrastructureObjective)
			end
			PlayRadio("redsea-hodeidah-secure-ar.wav", "radio-hodeidah-secure-ar", "yemen-coast-command")
		end
	end)
end

InsideSurveillanceZone = function(actor)
	if not actor or actor.IsDead then return false end
	local location = actor.Location
	return location.X >= 20 and location.X <= 43 and location.Y >= 62 and location.Y <= 82
end

EvaluateSurveillanceSweep = function()
	UserInterface.SetMissionText("")
	local cameraOne = Actor.Create("camera", true, { Owner = Saudi, Location = SweepCameraOne.Location })
	local cameraTwo = Actor.Create("camera", true, { Owner = Saudi, Location = SweepCameraTwo.Location })
	local exposed = { }
	Utils.Do({ LauncherOne, LauncherTwo, TechnicalOne, TechnicalTwo }, function(actor)
		if InsideSurveillanceZone(actor) then exposed[#exposed + 1] = actor end
	end)

	if #exposed <= Settings.AllowedExposed then
		DispersalComplete = true
		Yemen.MarkCompletedObjective(DisperseObjective)
	else
		PlayRadio("redsea-hodeidah-strike-en.wav", "radio-hodeidah-strike-en", "surveillance-net")
		Yemen.MarkFailedObjective(DisperseObjective)
		for i, actor in ipairs(exposed) do
			local attacker = Actor.Create("m1a2s", true,
				{ Owner = Saudi, Location = NorthEntry.Location + CVec.New(i % 3, math.floor(i / 3)) })
			attacker.Attack(actor)
			HuntOnIdle(attacker)
		end
	end

	Trigger.AfterDelay(DateTime.Seconds(12), function()
		if not cameraOne.IsDead then cameraOne.Destroy() end
		if not cameraTwo.IsDead then cameraTwo.Destroy() end
	end)
end

WarnSurveillanceSweep = function()
	PlayRadio("redsea-hodeidah-sweep-ar.wav", "radio-hodeidah-sweep-ar", "surveillance-net")
	UserInterface.SetMissionText(UserInterface.GetFluentMessage("disperse-mobile-forces"), Yemen.Color)
	Trigger.AfterDelay(DateTime.Seconds(15), EvaluateSurveillanceSweep)
end

CriticalInfrastructureLost = function()
	if InfrastructureLost then return end
	InfrastructureLost = true
	PlayRadio("redsea-hodeidah-infrastructure-lost-en.wav",
		"radio-hodeidah-infrastructure-lost-en", "hodeidah-control")
	Yemen.MarkFailedObjective(ProtectInfrastructureObjective)
end

WorldLoaded = function()
	Yemen = Player.GetPlayer("Yemen")
	Saudi = Player.GetPlayer("Saudi Arabia")
	Civilians = Player.GetPlayer("Civilians")
	Settings = DifficultySettings[Map.LobbyOptionOrDefault("difficulty", "normal")]

	InitObjectives(Yemen)
	SaudiObjective = AddPrimaryObjective(Saudi, "")
	ProtectInfrastructureObjective = AddPrimaryObjective(Yemen, "protect-lifeline-infrastructure")
	DeliverReliefObjective = AddPrimaryObjective(Yemen, "deliver-relief-supplies")
	DisperseObjective = AddPrimaryObjective(Yemen, "disperse-mobile-forces")
	EvacuationObjective = AddPrimaryObjective(Yemen, "preserve-evacuation-route")

	Trigger.OnAnyKilled({ PortControl, FisheriesDepot, CoastalClinic }, CriticalInfrastructureLost)
	Trigger.AfterDelay(DateTime.Seconds(8), StartReliefConvoy)
	Trigger.AfterDelay(DateTime.Seconds(Settings.SweepDelay - 15), WarnSurveillanceSweep)
	Trigger.AfterDelay(DateTime.Seconds(25),
		function() SendSaudiWave(WestEntry, PortRally, Settings.WaveSize) end)
	Trigger.AfterDelay(DateTime.Seconds(78),
		function() SendSaudiWave(NorthEntry, ReliefTwo, Settings.WaveSize) end)

	Camera.Position = PortCamera.CenterPosition
	Trigger.AfterDelay(DateTime.Seconds(1), function()
		Camera.Position = PortCamera.CenterPosition
	end)
	PlayRadio("redsea-hodeidah-opening-ar.wav", "radio-hodeidah-opening-ar", "yemen-coast-command")
end

Tick = function()
	if Yemen.HasNoRequiredUnits() and not Yemen.IsObjectiveFailed(DeliverReliefObjective) then
		Yemen.MarkFailedObjective(DeliverReliefObjective)
		Saudi.MarkCompletedObjective(SaudiObjective)
	end
end
