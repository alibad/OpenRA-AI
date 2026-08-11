--[[
   Copyright (c) The OpenRA Developers and Contributors
   This file is part of OpenRA, which is free software. It is made
   available to you under the terms of the GNU General Public License
   as published by the Free Software Foundation, either version 3 of
   the License, or (at your option) any later version. For more
   information, see COPYING.
]]

-- Patched only in ephemeral engine-validation packages. The distributable
-- mission always ships with "live" and exposes no test lobby control.
MANDAB_TEST_PATH = "live"

DifficultySettings = {
	easy = {
		ReadinessSeconds = 540, ReconSeconds = 180, ThreatSeconds = 210,
		RequiredShips = 2, ReplacementShips = 1, GroundWaveSize = 4,
		DroneCount = 2, HoldSeconds = 45, ExtraLaunchers = 0
	},
	normal = {
		ReadinessSeconds = 450, ReconSeconds = 145, ThreatSeconds = 165,
		RequiredShips = 3, ReplacementShips = 1, GroundWaveSize = 6,
		DroneCount = 3, HoldSeconds = 60, ExtraLaunchers = 0
	},
	hard = {
		ReadinessSeconds = 360, ReconSeconds = 110, ThreatSeconds = 130,
		RequiredShips = 4, ReplacementShips = 0, GroundWaveSize = 8,
		DroneCount = 4, HoldSeconds = 80, ExtraLaunchers = 1
	}
}

ShipPaths = {
	{ ShipWestOne.Location, ShipWestTwo.Location, ShipWestThree.Location, ShipWestFour.Location, ShipWestExit.Location },
	{ ShipInnerWestOne.Location, ShipInnerWestTwo.Location, ShipInnerWestThree.Location, ShipInnerWestFour.Location, ShipInnerWestExit.Location },
	{ ShipInnerEastOne.Location, ShipInnerEastTwo.Location, ShipInnerEastThree.Location, ShipInnerEastFour.Location, ShipInnerEastExit.Location },
	{ ShipEastOne.Location, ShipEastTwo.Location, ShipEastThree.Location, ShipEastFour.Location, ShipEastExit.Location }
}

ShipEntries = { ShipEntryWest, ShipEntryInnerWest, ShipEntryInnerEast, ShipEntryEast }

ReadinessActive = false
ReconActive = false
ThreatActive = false
ShippingActive = false
ShippingComplete = false
HoldActive = false
MissionFailed = false
OptionalFailed = false
ReconScanned = { north = false, center = false, south = false }
ReconCount = 0
ThreatTotal = 3
ThreatsDestroyed = 0
Ships = { }
ShipsSecured = 0
ShipsLost = 0
ShipSequence = 0
RecoveryAnnouncements = 0

PlayRadio = function(file, message, speaker)
	Media.PlaySound(file)
	Media.DisplayMessage(UserInterface.GetFluentMessage(message), UserInterface.GetFluentMessage(speaker))
end

SecondsRemaining = function(deadline)
	return math.max(0, math.ceil((deadline - DateTime.GameTime) / DateTime.Seconds(1)))
end

ObjectiveOpen = function(objective)
	return not Saudi.IsObjectiveCompleted(objective) and not Saudi.IsObjectiveFailed(objective)
end

FailPrimary = function(objective)
	if MissionFailed or not ObjectiveOpen(objective) then return end
	MissionFailed = true
	Saudi.MarkFailedObjective(objective)
	Yemen.MarkCompletedObjective(YemenObjective)
	UserInterface.SetMissionText("")
	PlayRadio("redsea-mandab-failure-en.wav", "radio-mandab-failure-en", "mandab-control")
end

FailReadiness = function() FailPrimary(ReadinessObjective) end
FailRecon = function() FailPrimary(ReconObjective) end
FailThreats = function() FailPrimary(ThreatObjective) end
FailShipping = function() FailPrimary(ShippingObjective) end
FailPassage = function() FailPrimary(HoldObjective) end

CreateTemporaryCamera = function(location, seconds)
	local camera = Actor.Create("camera", true, { Owner = Saudi, Location = location })
	Trigger.AfterDelay(DateTime.Seconds(seconds), function()
		if not camera.IsDead then camera.Destroy() end
	end)
end

SaudiRosterCount = function()
	return #Saudi.GetActorsByType("m1a2s") + #Saudi.GetActorsByType("sads")
end

ActivateRecon = function()
	if ReconActive or MissionFailed then return end
	ReconActive = true
	ReconDeadline = DateTime.GameTime + DateTime.Seconds(Settings.ReconSeconds)
	Saudi.MarkCompletedObjective(ReadinessObjective)
	CreateTemporaryCamera(ReconNorth.Location, 7)
	CreateTemporaryCamera(ReconCenter.Location, 7)
	CreateTemporaryCamera(ReconSouth.Location, 7)
	Trigger.AfterDelay(DateTime.Seconds(3), function()
		PlayRadio("redsea-mandab-readiness-en.wav", "radio-mandab-readiness-en", "saudi-maritime-command")
	end)
end

ScanSector = function(name, id)
	if not ReconActive or ReconScanned[name] or MissionFailed then return end
	ReconScanned[name] = true
	ReconCount = ReconCount + 1
	Trigger.RemoveProximityTrigger(id)
	if ReconCount >= 3 then
		ActivateThreatPhase()
	end
end

BindReconTrigger = function(name, waypoint)
	Trigger.OnEnteredProximityTrigger(waypoint.CenterPosition, WDist.FromCells(4), function(actor, id)
		-- Scripted reveal cameras must not satisfy the player's reconnaissance.
		if actor.Owner == Saudi and actor.Type ~= "camera" then ScanSector(name, id) end
	end)
end

BindThreat = function(actor)
	Trigger.OnKilled(actor, function()
		ThreatsDestroyed = ThreatsDestroyed + 1
		if ThreatActive and ThreatsDestroyed >= ThreatTotal then
			StartCivilianShipping()
		end
	end)
end

ActivateThreatPhase = function()
	if ThreatActive or MissionFailed then return end
	ReconActive = false
	ThreatActive = true
	ThreatDeadline = DateTime.GameTime + DateTime.Seconds(Settings.ThreatSeconds)
	Saudi.MarkCompletedObjective(ReconObjective)

	ThreatNorth.Patrol({ ThreatNorth.Location, ThreatNorthPatrol.Location }, true, DateTime.Seconds(2))
	ThreatCenter.Patrol({ ThreatCenter.Location, ThreatCenterPatrol.Location }, true, DateTime.Seconds(2))
	ThreatSouth.Patrol({ ThreatSouth.Location, ThreatSouthPatrol.Location }, true, DateTime.Seconds(2))
	ThreatGuardNorth.Guard(ThreatNorth)
	ThreatGuardCenter.Guard(ThreatCenter)
	ThreatGuardSouth.Guard(ThreatSouth)

	if Settings.ExtraLaunchers > 0 then
		local extra = Actor.Create("ymlr", true, { Owner = Yemen, Location = CPos.New(88, 28) })
		ThreatTotal = ThreatTotal + 1
		BindThreat(extra)
		extra.Patrol({ CPos.New(88, 28), CPos.New(82, 33) }, true, DateTime.Seconds(1))
	end

	Utils.Do({ ReconNorth, ReconCenter, ReconSouth }, function(point)
		CreateTemporaryCamera(point.Location, 10)
	end)
	Trigger.AfterDelay(DateTime.Seconds(3), function()
		PlayRadio("redsea-mandab-recon-ar.wav", "radio-mandab-recon-ar", "saudi-maritime-command")
	end)
	if ThreatsDestroyed >= ThreatTotal then StartCivilianShipping() end
end

ActiveShipCount = function()
	local alive = 0
	for _, state in ipairs(Ships) do
		if not state.destroyed and not state.secured and state.actor and not state.actor.IsDead then alive = alive + 1 end
	end
	return alive
end

PotentialShipCount = function()
	return ShipsSecured + ActiveShipCount() + ReplacementShipsRemaining
end

IssueShipMove = function(state)
	if state.destroyed or state.secured or state.actor.IsDead then return end
	if state.step > #state.path then
		SecureShip(state)
		return
	end
	state.destination = state.path[state.step]
	state.actor.Move(state.destination)
end

SecureShip = function(state)
	if state.destroyed or state.secured then return end
	state.secured = true
	ShipsSecured = ShipsSecured + 1
	state.actor.Destroy()
	UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-shipping",
		{ ["secured"] = ShipsSecured, ["required"] = Settings.RequiredShips }), Saudi.Color)
	if ShipsSecured >= Settings.RequiredShips and not ShippingComplete then
		ShippingComplete = true
		Saudi.MarkCompletedObjective(ShippingObjective)
		Trigger.AfterDelay(DateTime.Seconds(4), StartFinalEscalation)
	end
end

OnShipKilled = function(state)
	if state.secured or state.destroyed then return end
	state.destroyed = true
	ShipsLost = ShipsLost + 1
	PlayRadio("redsea-mandab-loss-en.wav", "radio-mandab-loss-en", "civilian-shipping")

	if ReplacementShipsRemaining > 0 and ShipsSecured + ActiveShipCount() < Settings.RequiredShips then
		ReplacementShipsRemaining = ReplacementShipsRemaining - 1
		Trigger.AfterDelay(DateTime.Seconds(6), function() SpawnShip(state.lane, true) end)
	end

	if PotentialShipCount() < Settings.RequiredShips then FailShipping() end
end

SpawnShip = function(lane, replacement)
	ShipSequence = ShipSequence + 1
	local actor = Actor.Create("lst", true, { Owner = Civilians, Location = ShipEntries[lane].Location })
	local state = {
		actor = actor, lane = lane, path = ShipPaths[lane], step = 1,
		lastLocation = actor.Location, stallChecks = 0, recoveries = 0,
		destroyed = false, secured = false, replacement = replacement
	}
	Ships[#Ships + 1] = state
	Trigger.OnKilled(actor, function() OnShipKilled(state) end)
	IssueShipMove(state)
end

RecoverShip = function(state, separated)
	if state.actor.IsDead or state.destroyed or state.secured then return end
	state.recoveries = state.recoveries + 1
	RecoveryAnnouncements = RecoveryAnnouncements + 1
	if state.recoveries == 1 or separated then
		PlayRadio("redsea-mandab-recovery-ar.wav", "radio-mandab-recovery-ar", "civilian-shipping")
	end
	UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-recovery",
		{ ["recoveries"] = RecoveryAnnouncements }), Saudi.Color)
	state.actor.Stop()
	IssueShipMove(state)
end

MonitorShips = function()
	if not ShippingActive or MissionFailed then return end
	local leadStep = 1
	for _, state in ipairs(Ships) do
		if not state.destroyed and not state.secured then leadStep = math.max(leadStep, state.step) end
	end

	for _, state in ipairs(Ships) do
		if not state.destroyed and not state.secured and not state.actor.IsDead then
			local location = state.actor.Location
			if state.destination and location.X == state.destination.X and location.Y == state.destination.Y then
				state.step = state.step + 1
				state.stallChecks = 0
				IssueShipMove(state)
			elseif location.X == state.lastLocation.X and location.Y == state.lastLocation.Y then
				state.stallChecks = state.stallChecks + 1
			else
				state.stallChecks = 0
			end

			if leadStep - state.step >= 2 then
				state.step = math.min(#state.path, leadStep - 1)
				state.stallChecks = 0
				RecoverShip(state, true)
			elseif state.stallChecks == 3 then
				RecoverShip(state, false)
			elseif state.stallChecks >= 6 then
				-- Last-resort deterministic relocation prevents a permanently blocked
				-- civilian actor from deadlocking the mission. The destination is a
				-- validated water waypoint on that vessel's private lane.
				state.actor.Stop()
				state.actor.Teleport(state.path[state.step])
				state.step = state.step + 1
				state.stallChecks = 0
				RecoverShip(state, false)
			end
			state.lastLocation = location
		end
	end
end

StartCivilianShipping = function()
	if ShippingActive or MissionFailed then return end
	ThreatActive = false
	ShippingActive = true
	ReplacementShipsRemaining = Settings.ReplacementShips
	Saudi.MarkCompletedObjective(ThreatObjective)
	CreateTemporaryCamera(FleetCamera.Location, 12)
	Trigger.AfterDelay(DateTime.Seconds(3), function()
		PlayRadio("redsea-mandab-shipping-en.wav", "radio-mandab-shipping-en", "civilian-shipping")
	end)
	for lane = 1, 4 do SpawnShip(lane, false) end
	Trigger.AfterDelay(DateTime.Seconds(12), function() SendDroneWave(math.max(1, Settings.DroneCount - 1)) end)
end

HuntOnIdle = function(actor)
	if actor and not actor.IsDead then Trigger.OnIdle(actor, actor.Hunt) end
end

SendGroundWave = function(entry, amount)
	local types = { "tech", "e1", "e2", "ymlr" }
	for i = 1, amount do
		local unit = Actor.Create(types[((i - 1) % #types) + 1], true,
			{ Owner = Yemen, Location = entry.Location + CVec.New(i % 3, math.floor(i / 3)) })
		unit.AttackMove(PassageControl.Location)
		HuntOnIdle(unit)
	end
end

SendDroneWave = function(amount)
	for i = 1, amount do
		local drone = Actor.Create("samad", true,
			{ Owner = Yemen, Location = DroneEntryWest.Location + CVec.New(0, i - 1) })
		local target = PassageControl
		for _, state in ipairs(Ships) do
			if not state.destroyed and not state.secured and not state.actor.IsDead then
				target = state.actor
				break
			end
		end
		drone.Attack(target)
		HuntOnIdle(drone)
	end
end

StartFinalEscalation = function()
	if HoldActive or MissionFailed then return end
	HoldActive = true
	HoldDeadline = DateTime.GameTime + DateTime.Seconds(Settings.HoldSeconds)
	PlayRadio("redsea-mandab-final-ar.wav", "radio-mandab-final-ar", "saudi-maritime-command")
	CreateTemporaryCamera(PassageControl.Location, 8)

	if not OptionalFailed then
		Trigger.AfterDelay(DateTime.Seconds(5), function()
			Actor.Create("m1a2s", true, { Owner = Saudi, Location = BaseRally.Location + CVec.New(-2, 0) })
			Actor.Create("sads", true, { Owner = Saudi, Location = BaseRally.Location + CVec.New(2, 0) })
		end)
	end

	SendGroundWave(NorthGroundEntry, Settings.GroundWaveSize)
	Trigger.AfterDelay(DateTime.Seconds(12), function() SendDroneWave(Settings.DroneCount) end)
	Trigger.AfterDelay(DateTime.Seconds(24), function() SendGroundWave(SouthGroundEntry, Settings.GroundWaveSize) end)
	if Settings.HoldSeconds >= 70 then
		Trigger.AfterDelay(DateTime.Seconds(45), function() SendDroneWave(Settings.DroneCount) end)
	end
end

NavigationBeaconLost = function()
	if OptionalFailed then return end
	OptionalFailed = true
	if ObjectiveOpen(BeaconObjective) then Saudi.MarkFailedObjective(BeaconObjective) end
	PlayRadio("redsea-mandab-beacon-lost-en.wav", "radio-mandab-beacon-lost-en", "mandab-control")
end

CompleteMission = function()
	if MissionFailed or Saudi.IsObjectiveCompleted(HoldObjective) then return end
	HoldActive = false
	UserInterface.SetMissionText("")
	Saudi.MarkCompletedObjective(HoldObjective)
	if not OptionalFailed and ObjectiveOpen(BeaconObjective) then Saudi.MarkCompletedObjective(BeaconObjective) end
	Trigger.AfterDelay(DateTime.Seconds(3), function()
		PlayRadio("redsea-mandab-victory-ar.wav", "radio-mandab-victory-ar", "mandab-control")
	end)
end

ApplyValidationScenario = function()
	if MANDAB_TEST_PATH == "live" then return end
	Trigger.AfterDelay(DateTime.Seconds(2), function()
		if MANDAB_TEST_PATH == "headless-victory" then
			-- The validation package uses the real world, actors, callbacks, vessel
			-- movement, recovery monitor, and final waves. It only accelerates the
			-- player-driven setup steps so CI does not need UI-level construction.
			Settings.HoldSeconds = 6
			ReadinessActive = false
			ActivateRecon()
			Trigger.AfterDelay(DateTime.Seconds(1), function()
				ReconActive = false
				ActivateThreatPhase()
			end)
			Trigger.AfterDelay(DateTime.Seconds(2), function()
				ThreatNorth.Kill()
				ThreatCenter.Kill()
				ThreatSouth.Kill()
			end)
		elseif MANDAB_TEST_PATH == "fail-readiness" then
			FailReadiness()
		elseif MANDAB_TEST_PATH == "fail-recon" then
			Saudi.MarkCompletedObjective(ReadinessObjective)
			FailRecon()
		elseif MANDAB_TEST_PATH == "fail-threats" then
			Saudi.MarkCompletedObjective(ReadinessObjective)
			Saudi.MarkCompletedObjective(ReconObjective)
			FailThreats()
		elseif MANDAB_TEST_PATH == "fail-shipping" then
			Saudi.MarkCompletedObjective(ReadinessObjective)
			Saudi.MarkCompletedObjective(ReconObjective)
			Saudi.MarkCompletedObjective(ThreatObjective)
			FailShipping()
		elseif MANDAB_TEST_PATH == "fail-passage" then
			Saudi.MarkCompletedObjective(ReadinessObjective)
			Saudi.MarkCompletedObjective(ReconObjective)
			Saudi.MarkCompletedObjective(ThreatObjective)
			Saudi.MarkCompletedObjective(ShippingObjective)
			FailPassage()
		end
	end)
end

WorldLoaded = function()
	Saudi = Player.GetPlayer("Saudi Arabia")
	Yemen = Player.GetPlayer("Yemen")
	Civilians = Player.GetPlayer("Civilian Shipping")
	Settings = DifficultySettings[Map.LobbyOptionOrDefault("difficulty", "normal")]

	InitObjectives(Saudi)
	YemenObjective = AddPrimaryObjective(Yemen, "")
	ReadinessObjective = AddPrimaryObjective(Saudi, "establish-coastal-post")
	ReconObjective = AddPrimaryObjective(Saudi, "reconnoiter-coast")
	ThreatObjective = AddPrimaryObjective(Saudi, "neutralize-mobile-threats")
	ShippingObjective = AddPrimaryObjective(Saudi, "escort-civilian-shipping")
	HoldObjective = AddPrimaryObjective(Saudi, "hold-safe-passage")
	BeaconObjective = AddSecondaryObjective(Saudi, "preserve-navigation-beacons")

	ReadinessActive = true
	ReadinessDeadline = DateTime.GameTime + DateTime.Seconds(Settings.ReadinessSeconds)
	BindReconTrigger("north", ReconNorth)
	BindReconTrigger("center", ReconCenter)
	BindReconTrigger("south", ReconSouth)
	BindThreat(ThreatNorth)
	BindThreat(ThreatCenter)
	BindThreat(ThreatSouth)

	Trigger.OnAnyKilled({ SaudiConyard, SaudiRefinery }, function()
		if ReadinessActive then FailReadiness() end
	end)
	Trigger.OnKilled(PassageControl, FailPassage)
	Trigger.OnAnyKilled({ NavigationBeaconNorth, NavigationBeaconSouth }, NavigationBeaconLost)

	Camera.Position = BaseCamera.CenterPosition
	Trigger.AfterDelay(DateTime.Seconds(1), function() Camera.Position = BaseCamera.CenterPosition end)
	-- Let the objective notifications clear before the first bilingual subtitle.
	Trigger.AfterDelay(DateTime.Seconds(7), function()
		PlayRadio("redsea-mandab-opening-ar.wav", "radio-mandab-opening-ar", "mandab-control")
	end)
	ApplyValidationScenario()
end

Tick = function()
	if MissionFailed then return end

	if DateTime.GameTime % DateTime.Seconds(1) == 0 then
		if ReadinessActive then
			if Saudi.HasPrerequisites({ "atek" }) and SaudiRosterCount() >= 3 then
				ReadinessActive = false
				ActivateRecon()
			elseif DateTime.GameTime >= ReadinessDeadline then
				FailReadiness()
			else
				UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-readiness",
					{ ["seconds"] = SecondsRemaining(ReadinessDeadline) }), Saudi.Color)
			end
		elseif ReconActive then
			if DateTime.GameTime >= ReconDeadline then
				FailRecon()
			else
				UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-recon",
					{ ["scanned"] = ReconCount, ["seconds"] = SecondsRemaining(ReconDeadline) }), Saudi.Color)
			end
		elseif ThreatActive then
			if DateTime.GameTime >= ThreatDeadline then
				FailThreats()
			else
				UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-threats",
					{ ["remaining"] = math.max(0, ThreatTotal - ThreatsDestroyed),
					  ["seconds"] = SecondsRemaining(ThreatDeadline) }), Saudi.Color)
			end
		elseif ShippingActive and not ShippingComplete then
			UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-shipping",
				{ ["secured"] = ShipsSecured, ["required"] = Settings.RequiredShips }), Saudi.Color)
		elseif HoldActive then
			if PassageControl.IsDead or Saudi.HasNoRequiredUnits() then
				FailPassage()
			elseif DateTime.GameTime >= HoldDeadline then
				CompleteMission()
			else
				UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-hold",
					{ ["seconds"] = SecondsRemaining(HoldDeadline) }), Saudi.Color)
			end
		end
	end

	if ShippingActive and DateTime.GameTime % DateTime.Seconds(2) == 0 then MonitorShips() end
end
