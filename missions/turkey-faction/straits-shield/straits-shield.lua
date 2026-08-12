-- Fictional combined land, drone, amphibious, and maritime construction mission.

DifficultySettings = {
	easy = { WaveSize = 2, WaveDelay = DateTime.Seconds(90) },
	normal = { WaveSize = 3, WaveDelay = DateTime.Seconds(72) },
	hard = { WaveSize = 5, WaveDelay = DateTime.Seconds(55) }
}

NetworkBuilt = false
HarborCaptured = false
UplinksDestroyed = 0
FleetDestroyed = 0
MissionEnded = false

PlayRadio = function(file, message)
	Media.PlaySound(file)
	Media.DisplayMessage(UserInterface.GetFluentMessage(message), UserInterface.GetFluentMessage("turkey-control"))
end

HuntOnIdle = function(actor)
	if actor and not actor.IsDead then
		Trigger.OnIdle(actor, actor.Hunt)
	end
end

TryVictory = function()
	if MissionEnded or not NetworkBuilt or not HarborCaptured or UplinksDestroyed < 3 or FleetDestroyed < 5 then
		return
	end

	MissionEnded = true
	Turkey.MarkCompletedObjective(SurfaceObjective)
	PlayRadio("turkey-mission-victory-tr.wav", "radio-victory")
	Trigger.AfterDelay(DateTime.Seconds(2), function()
		Media.PlaySound("turkey-mission-victory-en.wav")
	end)
end

OnUplinkDestroyed = function()
	if UplinksDestroyed >= 3 then return end
	UplinksDestroyed = UplinksDestroyed + 1
	local remaining = 3 - UplinksDestroyed
	UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-uplinks", { ["remaining"] = remaining }), Turkey.Color)
	PlayRadio("turkey-designate.wav", "radio-uplink")
	if UplinksDestroyed >= 3 then
		Turkey.MarkCompletedObjective(UplinkObjective)
		UserInterface.SetMissionText("")
	end
	TryVictory()
end

OnFleetLoss = function()
	FleetDestroyed = FleetDestroyed + 1
	local remaining = 5 - FleetDestroyed
	UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-fleet", { ["remaining"] = remaining }), Turkey.Color)
	if FleetDestroyed >= 5 then
		UserInterface.SetMissionText("")
	end
	TryVictory()
end

SendDroneWave = function()
	if MissionEnded or Orion.HasNoRequiredUnits() then return end
	PlayRadio("turkey-mission-opening-en.wav", "radio-wave")
	for i = 1, Settings.WaveSize do
		local entry = i % 2 == 0 and DroneEntryNorth or DroneEntryEast
		local type = i % 3 == 0 and "sahinx" or "kuzgunm"
		local drone = Actor.Create(type, true, { Owner = Orion, Location = entry.Location })
		if not TurkeyRefinery.IsDead then drone.Attack(TurkeyRefinery) else drone.Hunt() end
		HuntOnIdle(drone)
	end
	Trigger.AfterDelay(Settings.WaveDelay, SendDroneWave)
end

WorldLoaded = function()
	Turkey = Player.GetPlayer("Turkey")
	Orion = Player.GetPlayer("Orion Group")
	Civilians = Player.GetPlayer("Civilians")
	Settings = DifficultySettings[Map.LobbyOptionOrDefault("difficulty", "normal")]

	InitObjectives(Turkey)
	OrionObjective = AddPrimaryObjective(Orion, "")
	NetworkObjective = AddPrimaryObjective(Turkey, "build-combined-network")
	UplinkObjective = AddPrimaryObjective(Turkey, "destroy-drone-uplinks")
	HarborObjective = AddPrimaryObjective(Turkey, "capture-harbor-relay")
	SurfaceObjective = AddPrimaryObjective(Turkey, "neutralize-surface-group")
	YardObjective = AddSecondaryObjective(Turkey, "protect-construction-yard")

	Trigger.OnKilled(UplinkNorth, OnUplinkDestroyed)
	Trigger.OnKilled(UplinkEast, OnUplinkDestroyed)
	Trigger.OnKilled(UplinkSouth, OnUplinkDestroyed)

	Trigger.OnCapture(HarborRelay, function()
		if HarborCaptured then return end
		HarborCaptured = true
		Turkey.MarkCompletedObjective(HarborObjective)
		PlayRadio("turkey-mission-harbor-tr.wav", "radio-harbor")
		Trigger.AfterDelay(DateTime.Seconds(2), function() Media.PlaySound("turkey-mission-harbor-en.wav") end)
		TryVictory()
	end)
	Trigger.OnKilled(HarborRelay, function()
		if not HarborCaptured then Turkey.MarkFailedObjective(HarborObjective) end
	end)

	Utils.Do({ OrionFrigate, OrionCorvette1, OrionCorvette2, OrionUSV1, OrionUSV2 }, function(ship)
		Trigger.OnKilled(ship, OnFleetLoss)
		ship.AttackMove(NavalRally.Location)
	end)

	Trigger.OnKilled(TurkeyConyard, function()
		if MissionEnded then return end
		MissionEnded = true
		Turkey.MarkFailedObjective(YardObjective)
		PlayRadio("turkey-mission-opening-en.wav", "radio-yard-lost")
		Orion.MarkCompletedObjective(OrionObjective)
	end)

	Camera.Position = TurkeyCamera.CenterPosition
	Trigger.AfterDelay(DateTime.Seconds(1), function() Camera.Position = TurkeyCamera.CenterPosition end)
	PlayRadio("turkey-mission-opening-tr.wav", "radio-opening")
	Trigger.AfterDelay(DateTime.Seconds(2), function() Media.PlaySound("turkey-mission-opening-en.wav") end)
	Trigger.AfterDelay(DateTime.Seconds(70), SendDroneWave)
end

Tick = function()
	if MissionEnded then return end

	if not NetworkBuilt and Turkey.HasPrerequisites({ "weap", "dome", "fix", "hpad", "atek", "syrd" }) then
		NetworkBuilt = true
		Turkey.MarkCompletedObjective(NetworkObjective)
		PlayRadio("turkey-mission-tech-tr.wav", "radio-tech")
		Trigger.AfterDelay(DateTime.Seconds(2), function() Media.PlaySound("turkey-mission-tech-en.wav") end)
		TryVictory()
	end

	if Turkey.HasNoRequiredUnits() then
		MissionEnded = true
		Turkey.MarkFailedObjective(SurfaceObjective)
		Orion.MarkCompletedObjective(OrionObjective)
	end
end
