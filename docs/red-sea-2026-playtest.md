# Red Sea 2026 human playtest matrix

Automated checks prove that the mission loads, scripts initialize, assets
resolve, audio is valid, and packages are deterministic. They cannot prove that
combat feels fair or that the mix sounds right on a player's speakers.

Run `Play-Red-Sea-2026.cmd` three times for Jizan, then run the Yemen-side
mission once and record the following.

## Run 1: easy, mission comprehension

- Capture the radar without consulting this document.
- Confirm the English opening and Arabic radar/launcher lines are intelligible
  and that their bilingual subtitles remain readable during combat.
- Lose one truck intentionally; the mission should remain winnable with two.
- Target completion time: 12–20 minutes for a first-time player.

## Run 2: normal, intended experience

- Use both SADS vehicles to defeat the first drone wave.
- Verify launcher reveal cameras are long enough to understand both targets.
- Confirm west/east/south attacks create pressure without trapping the convoy.
- Listen at 50% music and 70% effects/speech: radio, Arabic acknowledgements,
  launch effects, and warning cues must remain distinct without clipping.
- Target completion time: 10–16 minutes after learning the route.

## Run 3: hard, mastery

- All three trucks must survive.
- Confirm eight-unit ambushes and four drones remain counterable with active
  scouting and air-defense positioning.
- Check that the convoy never stalls at Corridor One, Two, Three, or Port Gate.
- Target completion time: 12–18 minutes with no restart.

## Run 4: Hodeidah Lifeline, Yemen-side systems

Launch `.\scripts\play-red-sea-2026.ps1 -Mission hodeidah-lifeline-2026`.

- Confirm the starting construction, infantry, vehicle, and aircraft queues are
  populated, including the Tech Center progression and custom Yemen roster.
- Deliver the relief convoy, then move the missile launchers and technicals out
  of the marked surveillance zone before the sweep timer expires.
- Use at least one Samad against an armored target. It must approach at low
  altitude, detonate once at close range, display its dedicated impact, and be
  consumed rather than returning to the airfield.
- Preserve the required number of evacuation trucks and finish all four primary
  objectives without a script stall.
- Listen to all Arabic and English Hodeidah radio lines and confirm their mixed
  Unicode subtitles remain readable over combat.

## Base and production acceptance

- The construction and defense tabs are populated at mission start.
- The starting refinery supplies a working harvester and income loop.
- A war factory can be placed immediately with the starting cash.
- The vehicle queue contains the M1A2S and mobile air-defense system, but no
  legacy Allied tanks, jeep, artillery, radar jammer, or mine layer.
- The infantry queue contains no Spy and no Tanya entries.
- Replacement harvesters and an MCV become available through the normal tech
  tree.

## Visual acceptance

- Every ground vehicle rotates without a magenta fringe, clipped barrel, jump,
  backward-facing chassis, or inconsistent scale.
- Tank, air-defense, and technical turrets remain centered through 360 degrees.
- Launcher visibly switches to its empty state while reloading.
- The Samad silhouette remains legible above desert and structure backgrounds.
- Build icons are identifiable at normal UI scale.
- Destroy each custom ground vehicle once. Its wreck must preserve the correct
  silhouette and facing; no actor may disappear or turn into a stock 2TNK husk.

## Sign-off

Release quality requires all four runs without a blocker, no repeated pathing
stall, no inaudible mandatory instruction, and no dominant sound more than one
volume adjustment away from the stock Red Alert mix. Record difficulty,
completion time, surviving trucks, restart count, and any unclear instruction.
