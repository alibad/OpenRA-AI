# Bab al-Mandab Passage mission source

This is the third complete mission in **Red Sea 2026**. It is a playable Saudi
Arabia scenario and uses only actors already present in the Saudi/Yemen Red Sea
roster plus stock Red Alert campaign support and civilian transport actors.
It does not change shared actors, weapons, locomotors, aircraft, vehicle art, or
sprite pipelines.

The 96×96 deterministic terrain is intentionally stylized: the north-south
water channel, two coasts, and central Mayyun-shaped island communicate the
geographic relationship without claiming survey accuracy. Rebuild `map.bin`
with:

```powershell
.\.venv\Scripts\python.exe scripts\build-mandab-terrain.py missions\red-sea-2026\bab-al-mandab-passage\map.bin
```

Build and install the mission with:

```powershell
.\.venv\Scripts\python.exe scripts\build-red-sea-mission.py --mission bab-al-mandab-passage-2026
```

Launch it with:

```powershell
.\scripts\play-red-sea-2026.ps1 -Mission bab-al-mandab-passage-2026
```

Mission-specific synthetic voices use their own generator and provenance file:

```powershell
.\.venv\Scripts\python.exe scripts\generate-mandab-voices.py
```

The voices are generic Microsoft neural voices generated through `edge-tts`,
then radio-mastered with FFmpeg. They do not imitate a real person. See
`assets/red-sea-2026/mandab-voice-provenance.json` for every line, voice,
language, duration, and disclosure flag.

## Mission flow

1. Build a Radar Dome and Tech Center and produce another M1A2S or SADS.
2. Send Saudi units through all three coastal reconnaissance sectors.
3. Find and destroy the patrolling mobile launchers.
4. Protect the difficulty-dependent number of four civilian merchant vessels.
5. Hold Passage Control through the final combined-arms escalation.
6. Optionally preserve both civilian navigation beacons for final reinforcements.

Every merchant vessel has a private water lane. The script checks progress every
two seconds, reissues failed movement, catches separated ships up to the fleet,
and relocates a repeatedly blocked ship only to the next validated water
waypoint. Destroyed ships are accounted for immediately; easy and normal each
permit one replacement launch when survival would otherwise become impossible.

## Difficulty matrix

| Setting | Readiness | Recon | Threat hunt | Ships required | Replacements | Ground wave | Drones | Final hold |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Easy | 540 s | 180 s | 210 s | 2/4 | 1 | 4 | 2 | 45 s |
| Normal | 450 s | 145 s | 165 s | 3/4 | 1 | 6 | 3 | 60 s |
| Hard | 360 s | 110 s | 130 s | 4/4 | 0 | 8 | 4 | 80 s |

Hard also adds a fourth mobile launcher and a second late drone strike.

## Editorial boundary

Factual cutoff: **2026-08-11**. The public-source background and fictional
tactical layer are separated in `briefing.md`. All forces, routes, incidents,
positions, timings, dialogue, and outcomes are invented for play.

## Validation

Run the real-engine victory/failure matrix after packaging:

```powershell
.\.venv\Scripts\python.exe scripts\validate-mandab-mission.py
```

The validator sends synchronized construction, placement, production, and
reconnaissance orders to the unmodified distributable, then runs deterministic
ephemeral packages through victory and each of the five primary failure paths.
The latest local run completed production/recon at tick 3365, victory at tick
1400, and each failure path at tick 51. Evidence is written under
`artifacts/mandab-engine-validation/` and is intentionally not packaged.

The rendered pass covered 1280×720, 1920×1080, and 3840×2160 pseudo-fullscreen.
It verified the construction sidebar, shortened mission text, bilingual Unicode
subtitle wrapping, fleet camera reveal, four separate vessel lanes, and audible
opening radio. Screenshots are written under `artifacts/mandab-fullscreen/`.

## Remaining human judgments

Automation cannot decide whether normal/hard combat pressure feels fair or
whether speech, effects, and music are ideally mixed on a player's speakers.
A human release pass should still judge wave pacing, the 60/80-second holds,
Arabic pronunciation, and relative radio volume at the intended listening mix.
