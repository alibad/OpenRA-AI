-- Fictional combined-arms exercise. No real operation, targets, or leaders are represented.

DifficultySettings = {
	easy = { RequiredLandings = 1, GroundWave = 4, AirWave = 1, NavalWave = 1, Interval = 52 },
	normal = { RequiredLandings = 2, GroundWave = 6, AirWave = 2, NavalWave = 2, Interval = 42 },
	hard = { RequiredLandings = 2, GroundWave = 8, AirWave = 3, NavalWave = 3, Interval = 34 }
}

NetworkEstablished = false
LandingComplete = false
CommandDestroyed = false
LandingCount = 0
AmphibiousAnnounced = false
PassedSeaGate = { }
CountedLanding = { }
AmphibiousRouteOpened = false

PlayRadio = function(file, message, speaker)
	Media.PlaySound(file)
	Media.DisplayMessage(UserInterface.GetFluentMessage(message), UserInterface.GetFluentMessage(speaker))
end

HuntOnIdle = function(actor)
	if actor and not actor.IsDead then
		Trigger.OnIdle(actor, actor.Hunt)
	end
end

SendGroundWave = function()
	if CommandDestroyed then return end
	local types = { "e1", "e3", "3tnk", "v2rl" }
	for i = 1, Settings.GroundWave do
		local unit = Actor.Create(types[((i - 1) % #types) + 1], true,
			{ Owner = Obsidian, Location = GroundWaveEntry.Location + CVec.New(-(i % 3), math.floor(i / 3)) })
		unit.AttackMove(GroundWaveRally.Location)
		HuntOnIdle(unit)
	end
	Trigger.AfterDelay(DateTime.Seconds(Settings.Interval), SendGroundWave)
end

SendAirWave = function()
	local targets = { ChinaRadar, ChinaWarFactory, NetworkRelay }
	for i = 1, Settings.AirWave do
		local aircraft = Actor.Create(i % 2 == 0 and "mig" or "yak", true,
			{ Owner = Obsidian, Location = AirWaveEntry.Location + CVec.New(-i, 0) })
		aircraft.Attack(targets[((i - 1) % #targets) + 1])
		HuntOnIdle(aircraft)
	end
end

SendNavalWave = function()
	for i = 1, Settings.NavalWave do
		local ship = Actor.Create(i % 2 == 0 and "ss" or "dd", true,
			{ Owner = Obsidian, Location = NavalWaveEntry.Location + CVec.New(-i * 2, 0) })
		ship.AttackMove(NavalWaveRally.Location)
		HuntOnIdle(ship)
	end
end

CheckVictory = function()
	if NetworkEstablished and LandingComplete and CommandDestroyed then
		PlayRadio("china-haitan-secure-en.wav", "radio-haitan-secure-en", "exercise-control")
		China.MarkCompletedObjective(DestroyCommandObjective)
	end
end

EstablishNetwork = function(actor, id)
	if NetworkEstablished or actor.Owner ~= China or actor.Type ~= "cnnetwork" then return end
	NetworkEstablished = true
	Trigger.RemoveProximityTrigger(id)
	China.MarkCompletedObjective(NetworkObjective)
	UserInterface.SetMissionText("")
	Actor.Create("camera", true, { Owner = China, Location = EastCamera.Location })
	PlayRadio("china-haitan-network-en.wav", "radio-haitan-network-en", "exercise-control")
	Trigger.AfterDelay(DateTime.Seconds(5), SendAirWave)
	CheckVictory()
end

IsSeaDragon = function(actor)
	return actor == SeaDragonOne or actor == SeaDragonTwo or actor == SeaDragonThree or string.lower(actor.Type) == "cnzbd"
end

RegisterSeaGate = function(actor)
	if actor.Owner == China and IsSeaDragon(actor) then
		PassedSeaGate[actor] = true
		AmphibiousRouteOpened = true
		if not AmphibiousAnnounced then
			AmphibiousAnnounced = true
			PlayRadio("china-haitan-amphibious-zh.wav", "radio-haitan-amphibious-zh", "exercise-control")
		end
	end
end

RegisterLanding = function(actor)
	if actor.Owner ~= China or not IsSeaDragon(actor) or not AmphibiousRouteOpened or CountedLanding[actor] then return end
	CountedLanding[actor] = true
	LandingCount = LandingCount + 1
	UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-haitan-landing",
		{ ["landed"] = LandingCount, ["required"] = Settings.RequiredLandings }), China.Color)
	if LandingCount >= Settings.RequiredLandings and not LandingComplete then
		LandingComplete = true
		China.MarkCompletedObjective(LandingObjective)
		UserInterface.SetMissionText("")
		PlayRadio("china-haitan-combined-en.wav", "radio-haitan-combined-en", "exercise-control")
		Trigger.AfterDelay(DateTime.Seconds(3), SendNavalWave)
		CheckVictory()
	end
end

WorldLoaded = function()
	China = Player.GetPlayer("China")
	Obsidian = Player.GetPlayer("Obsidian Directorate")
	Settings = DifficultySettings[Map.LobbyOptionOrDefault("difficulty", "normal")]

	InitObjectives(China)
	ObsidianObjective = AddPrimaryObjective(Obsidian, "")
	NetworkObjective = AddPrimaryObjective(China, "deploy-network-specialist")
	LandingObjective = AddPrimaryObjective(China, "complete-amphibious-landing")
	DestroyCommandObjective = AddPrimaryObjective(China, "destroy-control-node")
	ProtectRelayObjective = AddSecondaryObjective(China, "protect-network-relay")

	Trigger.OnEnteredProximityTrigger(NetworkNode.CenterPosition, WDist.FromCells(2), EstablishNetwork)
	Trigger.OnEnteredProximityTrigger(AmphibiousGate.CenterPosition, WDist.FromCells(8), RegisterSeaGate)
	Trigger.OnEnteredProximityTrigger(EastBeach.CenterPosition, WDist.FromCells(3), RegisterLanding)
	Trigger.OnKilled(NetworkRelay, function()
		China.MarkFailedObjective(ProtectRelayObjective)
	end)
	Trigger.OnKilled(EnemyCommand, function()
		CommandDestroyed = true
		CheckVictory()
	end)
	Trigger.OnAllKilled({ JammerOne, JammerTwo, JammerThree }, function()
		Actor.Create("camera", true, { Owner = China, Location = EnemyCommand.Location })
	end)

	Camera.Position = WestCamera.CenterPosition
	PlayRadio("china-haitan-opening-zh.wav", "radio-haitan-opening-zh", "exercise-control")
	UserInterface.SetMissionText(UserInterface.GetFluentMessage("mission-text-haitan-network"), China.Color)
	Trigger.AfterDelay(DateTime.Seconds(24), function()
		PlayRadio("china-haitan-warning-zh.wav", "radio-haitan-warning-zh", "exercise-control")
		SendGroundWave()
	end)
end

Tick = function()
	if China.HasNoRequiredUnits() and not China.IsObjectiveFailed(NetworkObjective) then
		China.MarkFailedObjective(NetworkObjective)
		China.MarkFailedObjective(LandingObjective)
		China.MarkFailedObjective(DestroyCommandObjective)
		Obsidian.MarkCompletedObjective(ObsidianObjective)
	end
end
