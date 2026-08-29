from __future__ import annotations

import hashlib
import json
import math
import os
import re
import runpy
import subprocess
import struct
import unittest
import wave
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
BITS = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
COMMON = ROOT / "engine" / "openra" / "mods" / "common"
SPRITE_FRAMES = ROOT / "generated" / "red-sea-sprites"
MISSION_SOURCE = ROOT / "missions" / "red-sea-2026" / "jizan-corridor"
MISSION_PACKAGE = ROOT / "generated" / "missions" / "jizan-corridor-2026.oramap"
HODEIDAH_SOURCE = ROOT / "missions" / "red-sea-2026" / "hodeidah-lifeline"
HODEIDAH_PACKAGE = ROOT / "generated" / "missions" / "hodeidah-lifeline-2026.oramap"
MANDAB_SOURCE = ROOT / "missions" / "red-sea-2026" / "bab-al-mandab-passage"
MANDAB_PACKAGE = ROOT / "generated" / "missions" / "bab-al-mandab-passage-2026.oramap"
ENGINE_ROOT = ROOT / "engine" / "openra"
UTILITY = ENGINE_ROOT / "bin" / ("OpenRA.Utility.exe" if os.name == "nt" else "OpenRA.Utility")


def _ttf_has_codepoint(data: bytes, codepoint: int) -> bool:
    """Read TrueType cmap format 4/12 without adding a fontTools dependency."""
    table_count = struct.unpack_from(">H", data, 4)[0]
    cmap_offset = None
    for index in range(table_count):
        record = 12 + index * 16
        if data[record:record + 4] == b"cmap":
            cmap_offset = struct.unpack_from(">I", data, record + 8)[0]
            break
    if cmap_offset is None:
        return False

    encoding_count = struct.unpack_from(">H", data, cmap_offset + 2)[0]
    subtables = []
    for index in range(encoding_count):
        record = cmap_offset + 4 + index * 8
        offset = cmap_offset + struct.unpack_from(">I", data, record + 4)[0]
        subtables.append(offset)

    for offset in subtables:
        format_number = struct.unpack_from(">H", data, offset)[0]
        if format_number == 12:
            group_count = struct.unpack_from(">I", data, offset + 12)[0]
            for group in range(group_count):
                start, end, glyph = struct.unpack_from(">III", data, offset + 16 + group * 12)
                if start <= codepoint <= end:
                    return glyph + codepoint - start != 0
        elif format_number == 4 and codepoint <= 0xFFFF:
            segment_count = struct.unpack_from(">H", data, offset + 6)[0] // 2
            end_codes = offset + 14
            start_codes = end_codes + segment_count * 2 + 2
            deltas = start_codes + segment_count * 2
            ranges = deltas + segment_count * 2
            for segment in range(segment_count):
                end = struct.unpack_from(">H", data, end_codes + segment * 2)[0]
                start = struct.unpack_from(">H", data, start_codes + segment * 2)[0]
                if not start <= codepoint <= end:
                    continue
                delta = struct.unpack_from(">h", data, deltas + segment * 2)[0]
                range_offset = struct.unpack_from(">H", data, ranges + segment * 2)[0]
                if range_offset == 0:
                    return (codepoint + delta) & 0xFFFF != 0
                glyph_offset = ranges + segment * 2 + range_offset + 2 * (codepoint - start)
                glyph = struct.unpack_from(">H", data, glyph_offset)[0]
                return glyph != 0 and (glyph + delta) & 0xFFFF != 0
    return False


class RedSeaAssetTests(unittest.TestCase):
    def _resolved_rules(self, actor: str) -> str:
        environment = os.environ.copy()
        environment["ENGINE_DIR"] = ".."
        environment["DOTNET_ROLL_FORWARD"] = "Major"
        result = subprocess.run(
            [str(UTILITY), "ra", "--resolved-rules", actor, str(MISSION_PACKAGE)],
            cwd=ENGINE_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout

    def test_new_factions_resolve_complete_inherited_build_trees(self) -> None:
        contracts = {
            "FACT": (
                ("saudialliedtree", "saudi", "structures.allies"),
                ("yemensoviettree", "yemen", "structures.soviet"),
            ),
            "WEAP": (
                ("saudialliedtree", "saudi", "vehicles.allies"),
                ("yemensoviettree", "yemen", "vehicles.soviet"),
            ),
            "HPAD": (("saudialliedtree", "saudi", "aircraft.allies"),),
            "AFLD": (("yemensoviettree", "yemen", "aircraft.soviet"),),
            "TENT": (("saudialliedtree", "saudi", "infantry.allies"),),
            "BARR": (("yemensoviettree", "yemen", "infantry.soviet"),),
            "SAFLD": (("saudi", "saudi", "aircraft.saudi"),),
            "SYRD": (("saudialliedtree", "saudi", "ships.allies"),),
            "SPEN": (("yemensoviettree", "yemen", "ships.soviet"),),
        }
        for actor, providers in contracts.items():
            resolved = self._resolved_rules(actor)
            for key, faction, prerequisite in providers:
                block = (
                    f"ProvidesPrerequisite@{key}:\n"
                    f"\tFactions: {faction}\n"
                    f"\tPrerequisite: {prerequisite}"
                )
                self.assertIn(block, resolved, f"{actor} must provide {prerequisite} to {faction}")

    def test_ai_personalities_can_reach_and_control_the_custom_roster(self) -> None:
        resolved = self._resolved_rules("Player")
        for actor in ("m1a2s", "sads", "tech", "ymlr"):
            self.assertGreaterEqual(resolved.count(f"\t\t{actor}:"), 10, actor)
        self.assertGreaterEqual(resolved.count("\t\tsamad:"), 10)
        self.assertIn("TechTypes: dome, atek, stek, fix, afld, hpad, safld", resolved)
        self.assertIn("TechTypes: mslo, dome, atek, stek, fix, afld, hpad, safld", resolved)
        self.assertIn("ProductionTypes: barr,tent,weap,afld,hpad,safld", resolved)
        for actor in ("SAMAD", "F15SA", "AH64SA"):
            air = self._resolved_rules(actor)
            self.assertIn("StrategicRole:", air)
            self.assertIn("Domain: air", air)

    def test_original_sprite_packages_have_expected_frames(self) -> None:
        expected = {
            "m1a2s": 64,
            "sads": 64,
            "tech": 64,
            "ymlr": 64,
            "samad": 32,
            "f15sa": 16,
            "ah64sa": 32,
            "samadhusk": 16,
            "f15sahusk": 16,
            "ah64sahusk": 32,
            "ah64sarotor": 12,
            "m1a2shusk": 64,
            "sadshusk": 64,
            "techhusk": 64,
            "ymlrhusk": 32,
            "m1a2sicon": 1,
            "sadsicon": 1,
            "techicon": 1,
            "ymlricon": 1,
            "samadicon": 1,
            "redsea-m1-impact": 9,
            "redsea-m1-muzzle": 48,
            "redsea-drone-impact": 11,
        }
        for name, frames in expected.items():
            path = BITS / f"{name}.shp"
            minimum_size = 1_500 if frames == 1 else 3_000 if frames <= 16 else 5_000
            self.assertGreater(path.stat().st_size, minimum_size)
            with path.open("rb") as stream:
                self.assertEqual(struct.unpack("<H", stream.read(2))[0], frames, name)

    def test_ground_roster_uses_matching_directional_wrecks(self) -> None:
        rules = (ROOT / "engine" / "openra" / "mods" / "ra" / "rules" / "red-sea.yaml").read_text(encoding="utf-8")
        sequences = (ROOT / "engine" / "openra" / "mods" / "ra" / "sequences" / "red-sea.yaml").read_text(encoding="utf-8")
        for actor, husk in (
            ("M1A2S", "m1a2shusk"),
            ("SADS", "sadshusk"),
            ("TECH", "techhusk"),
            ("YMLR", "ymlrhusk"),
        ):
            self.assertIn(f"Actor: {actor}.Husk", rules)
            self.assertIn(f"Filename: {husk}.shp", sequences)

    def test_mission_objectives_ui_wraps_long_descriptions(self) -> None:
        chrome = (ROOT / "engine" / "openra" / "mods" / "common" / "chrome" / "ingame-infoobjectives.yaml").read_text(encoding="utf-8")
        logic = (ROOT / "engine" / "openra" / "OpenRA.Mods.Common" / "Widgets" / "Logic" / "Ingame" / "GameInfoObjectivesLogic.cs").read_text(encoding="utf-8")
        self.assertIn("Label@OBJECTIVE_DESCRIPTION:", chrome)
        self.assertIn("WordWrap: True", chrome)
        self.assertIn("description.IncreaseHeightToFitCurrentText();", logic)
        self.assertIn("description.Bounds.Bottom + 2", logic)

    def test_selectable_red_sea_factions_have_hidpi_flags(self) -> None:
        chrome = (ROOT / "engine" / "openra" / "mods" / "ra" / "chrome.yaml").read_text(encoding="utf-8")
        world_rules = (ROOT / "engine" / "openra" / "mods" / "ra" / "rules" / "world.yaml").read_text(encoding="utf-8")
        self.assertIn("\t\tsaudi: 226, 1, 30, 15", chrome)
        self.assertIn("\t\tyemen: 226, 17, 30, 15", chrome)
        self.assertIn("Image: glyphs-redsea.png", chrome)

        flag_block = chrome.split("flags:\n", 1)[1].split("\nmusic:\n", 1)[0]
        registered_flags = {
            line.strip().split(":", 1)[0]
            for line in flag_block.splitlines()
            if line.startswith("\t\t") and ":" in line
        }
        selectable_factions = set()
        for faction_block in re.findall(r"(?m)^\tFaction@[^:]+:\n((?:\t\t.*\n?)*)", world_rules):
            if "\n\t\tSelectable: False" in faction_block:
                continue
            for line in faction_block.splitlines():
                if line.startswith("\t\tInternalName:"):
                    selectable_factions.add(line.split(":", 1)[1].strip())
        self.assertTrue(selectable_factions)
        self.assertEqual(set(), selectable_factions - registered_flags)

        for suffix, scale in (("", 1), ("-2x", 2), ("-3x", 3)):
            path = ROOT / "engine" / "openra" / "mods" / "ra" / "uibits" / f"glyphs-redsea{suffix}.png"
            source = ROOT / "engine" / "openra" / "mods" / "ra" / "uibits" / f"glyphs{suffix}.png"
            with Image.open(path) as atlas:
                with Image.open(source) as original:
                    self.assertEqual(atlas.width, original.width)
                    self.assertGreaterEqual(atlas.height, original.height)
                saudi = atlas.crop((226 * scale, 1 * scale, 256 * scale, 16 * scale)).convert("RGB")
                yemen = atlas.crop((226 * scale, 17 * scale, 256 * scale, 32 * scale)).convert("RGB")
                self.assertIn((0, 108, 53), set(saudi.get_flattened_data()))
                self.assertIn((206, 17, 38), set(yemen.get_flattened_data()))

    def test_custom_units_use_native_sized_dedicated_production_cameos(self) -> None:
        sequences = (ROOT / "engine" / "openra" / "mods" / "ra" / "sequences" / "red-sea.yaml").read_text(encoding="utf-8")
        for name in ("m1a2s", "sads", "tech", "ymlr", "samad"):
            icon_name = f"{name}icon"
            self.assertIn(f"Filename: {icon_name}.shp", sequences)
            frame_path = SPRITE_FRAMES / icon_name / f"{icon_name}-0000.png"
            with Image.open(frame_path) as frame:
                self.assertEqual(frame.size, (64, 48), icon_name)
                self.assertEqual(frame.mode, "P", icon_name)
                self.assertNotIn(0, frame.tobytes(), f"{icon_name} must be fully opaque like native RA cameos")
            self.assertGreater((BITS / f"{icon_name}.shp").stat().st_size, 1_500, icon_name)

    def test_vehicle_sprites_match_native_red_alert_scale(self) -> None:
        expected = {
            "m1a2s": (40, 39, 32),
            "sads": (40, 35, 32),
            "tech": (28, 27, 32),
            "ymlr": (40, 37, 32),
            "samad": (40, 37, 16),
        }
        for name, (canvas, max_extent, facings) in expected.items():
            paths = sorted((SPRITE_FRAMES / name).glob(f"{name}-*.png"))[:facings]
            self.assertEqual(len(paths), facings, name)
            extents = []
            for path in paths:
                with Image.open(path) as frame:
                    self.assertEqual(frame.size, (canvas, canvas), path.name)
                    bounds = frame.convert("RGBA").getchannel("A").getbbox()
                self.assertIsNotNone(bounds, path.name)
                extents.append(max(bounds[2] - bounds[0], bounds[3] - bounds[1]))
            self.assertLessEqual(max(extents), max_extent, name)

    def test_every_custom_unit_uses_true_directional_geometry(self) -> None:
        builder = runpy.run_path(str(ROOT / "scripts" / "build-red-sea-sprites.py"))
        for name in ("m1a2s", "sads", "tech", "ymlr", "samad"):
            definition = builder["ASSETS"][name]
            self.assertEqual(definition["directional_model"], name)
            self.assertEqual(definition["facings"], 16 if name == "samad" else 32)
            for forbidden in ("source", "base_angles", "projection_y"):
                self.assertNotIn(forbidden, definition, f"{name} must not rotate flat source art")

    def test_ground_models_use_exact_classic_red_alert_yaws(self) -> None:
        renderer = runpy.run_path(str(ROOT / "scripts" / "red_sea_directional_vehicle.py"))
        yaws = renderer["CLASSIC_YAWS"]
        angles = renderer["_angles"](32, classic=True)
        self.assertEqual(len(yaws), 32)
        self.assertEqual(yaws[:8], (0, 40, 74, 112, 146, 172, 200, 228))
        self.assertEqual(yaws[-4:], (882, 914, 948, 984))
        # Native RA frame 8 presents the vehicle nose on screen-left and frame
        # 24 presents it on screen-right. The renderer therefore consumes the
        # engine yaw ring with negative screen rotation, not positive rotation.
        self.assertEqual(angles[0], 0)
        self.assertEqual(angles[8], -90)
        self.assertEqual(angles[16], -180)
        self.assertEqual(angles[24], -270)
        self.assertNotEqual(abs(angles[1]), 360 / 32)

    def test_uniform_aircraft_facing_ring_uses_native_screen_handedness(self) -> None:
        renderer = runpy.run_path(str(ROOT / "scripts" / "red_sea_directional_vehicle.py"))
        angles = renderer["_angles"](16, classic=False)
        self.assertEqual((angles[0], angles[4], angles[8], angles[12]), (0, -90, -180, -270))

    def test_renderer_projects_front_marker_in_native_cardinal_order(self) -> None:
        renderer = runpy.run_path(str(ROOT / "scripts" / "red_sea_directional_vehicle.py"))
        mesh = renderer["Mesh"]()
        mesh.box(-0.8, 0.8, -0.8, 0.8, 0.1, 0.5, renderer["OLIVE"])
        mesh.box(-0.3, 0.3, -2.0, -1.4, 0.2, 0.8, renderer["LAMP"])
        angles = renderer["_angles"](32, classic=True)

        centroids = []
        for index in (0, 8, 16, 24):
            frame = renderer["_render"](mesh, angles[index], 40, shadow=False, model_span=5)
            marker = [
                (x, y)
                for y in range(frame.height)
                for x in range(frame.width)
                if (lambda color: color[3] and color[0] > 150 and color[1] > 120 and color[2] < 120)(
                    frame.getpixel((x, y))
                )
            ]
            self.assertGreater(len(marker), 10)
            centroids.append(
                (sum(x for x, _ in marker) / len(marker), sum(y for _, y in marker) / len(marker))
            )

        north, east, south, west = centroids
        self.assertLess(north[1], 20)  # front marker at screen top
        self.assertLess(east[0], 20)  # then screen left, matching native frame 8
        self.assertGreater(south[1], 20)  # then screen bottom
        self.assertGreater(west[0], 20)  # then screen right at native frame 24

    def test_m1_has_32_unique_hull_and_turret_frames_with_smooth_footprints(self) -> None:
        for start in (0, 32):
            frames = []
            for index in range(start, start + 32):
                path = SPRITE_FRAMES / "m1a2s" / f"m1a2s-{index:04d}.png"
                frame = Image.open(path).convert("RGBA")
                bounds = frame.getchannel("A").getbbox()
                self.assertIsNotNone(bounds, path.name)
                frames.append((frame, bounds))

            hashes = {hashlib.sha256(frame.tobytes()).digest() for frame, _ in frames}
            self.assertEqual(len(hashes), 32, "each facing must contain independently rendered geometry")

            widths = [bounds[2] - bounds[0] for _, bounds in frames]
            heights = [bounds[3] - bounds[1] for _, bounds in frames]
            self.assertLessEqual(max(abs(widths[(index + 1) % 32] - widths[index]) for index in range(32)), 5)
            self.assertLessEqual(max(abs(heights[(index + 1) % 32] - heights[index]) for index in range(32)), 4)

    def test_m1_facing_footprints_match_native_red_alert_proportions(self) -> None:
        north = Image.open(SPRITE_FRAMES / "m1a2s" / "m1a2s-0000.png").convert("RGBA")
        east = Image.open(SPRITE_FRAMES / "m1a2s" / "m1a2s-0008.png").convert("RGBA")
        north_bounds = north.getchannel("A").getbbox()
        east_bounds = east.getchannel("A").getbbox()
        self.assertIsNotNone(north_bounds)
        self.assertIsNotNone(east_bounds)
        north_width = north_bounds[2] - north_bounds[0]
        north_height = north_bounds[3] - north_bounds[1]
        east_width = east_bounds[2] - east_bounds[0]
        east_height = east_bounds[3] - east_bounds[1]
        self.assertGreaterEqual(north_width, 18)
        self.assertGreaterEqual(north_height, 16)
        self.assertGreaterEqual(east_width, 27)
        self.assertGreaterEqual(east_height, 14)
        self.assertLessEqual(abs(north_height - north_width), 4)
        self.assertGreater(east_width, east_height)

    def test_m1_combat_effects_are_directional_and_animated(self) -> None:
        builder = runpy.run_path(str(ROOT / "scripts" / "build-red-sea-sprites.py"))
        effects = builder["EFFECTS"]
        self.assertEqual(effects["redsea-m1-muzzle"]["facings"], 8)
        self.assertEqual(len(effects["redsea-m1-muzzle"]["scales"]), 6)
        self.assertEqual(len(effects["redsea-m1-impact"]["scales"]), 9)

    def test_samad_is_a_native_one_way_aircraft_with_a_projectile_dive(self) -> None:
        resolved = self._resolved_rules("SAMAD")
        rules = (ROOT / "engine" / "openra" / "mods" / "ra" / "rules" / "red-sea.yaml").read_text(encoding="utf-8")
        weapons = (ROOT / "engine" / "openra" / "mods" / "ra" / "weapons" / "red-sea.yaml").read_text(encoding="utf-8")
        self.assertIn("Weapon: RedSeaDroneStrike", resolved)
        self.assertIn("GrantConditionOnAttack@PAYLOAD:", resolved)
        self.assertIn("Condition: payload-released", resolved)
        self.assertIn("KillsSelf@PAYLOAD:", resolved)
        self.assertIn("RequiresCondition: payload-released", resolved)
        self.assertIn("AttackAircraft:", resolved)
        self.assertNotIn("AttackDive:", resolved)
        self.assertIn("MoveIntoShroud: true", resolved)
        self.assertIn("SoundFiles: redsea-drone-loiter.wav", resolved)
        self.assertNotIn("Rearmable:", resolved)
        self.assertNotIn("Actor: YAK.Husk", resolved)
        self.assertIn("Actor: SAMAD.Husk", resolved)
        self.assertNotIn("WithFacingSpriteBody@DIVE:", rules)
        drone_weapon = weapons.split("\nRedSeaDroneStrike:\n", 1)[1].split("\nRedSeaF15AAM:\n", 1)[0]
        self.assertIn("Projectile: Missile", drone_weapon)
        self.assertIn("Image: samad", drone_weapon)
        self.assertIn("Sequences: dive", drone_weapon)

    def test_drone_strike_has_dedicated_impact_animation(self) -> None:
        builder = runpy.run_path(str(ROOT / "scripts" / "build-red-sea-sprites.py"))
        effect = builder["EFFECTS"]["redsea-drone-impact"]
        self.assertEqual(len(effect["scales"]), 11)
        self.assertEqual(len(effect["opacities"]), 11)
        self.assertGreater(
            (ROOT / "assets" / "red-sea-2026" / "sprite-sources" / str(effect["source"])).stat().st_size,
            500_000,
        )

    def test_ra_ui_has_arabic_font_fallback_with_required_glyphs(self) -> None:
        regular = COMMON / "NotoSansArabic-Regular.ttf"
        bold = COMMON / "NotoSansArabic-Bold.ttf"
        self.assertGreater(regular.stat().st_size, 250_000)
        self.assertGreater(bold.stat().st_size, 275_000)
        mod_yaml = (ROOT / "engine" / "openra" / "mods" / "ra" / "mod.yaml").read_text(encoding="utf-8")
        self.assertIn("Font: common|FreeSansArabic.ttf", mod_yaml)
        self.assertIn("Font: common|FreeSansArabicBold.ttf", mod_yaml)
        self.assertIn("FallbackFonts: common|NotoSansArabic-Bold.ttf", mod_yaml)
        for path in (regular, bold):
            data = path.read_bytes()
            for codepoint in (0x0627, 0x0645, 0xFE8E):
                self.assertTrue(_ttf_has_codepoint(data, codepoint), f"{path.name} U+{codepoint:04X}")

    def test_all_red_sea_audio_is_openra_ready_and_has_headroom(self) -> None:
        paths = sorted(BITS.glob("redsea-*.wav")) + sorted(BITS.glob("rsa-*.wav")) + sorted(BITS.glob("rye-*.wav"))
        self.assertGreaterEqual(len(paths), 19)
        for path in paths:
            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getframerate(), 44_100, path.name)
                self.assertEqual(audio.getnchannels(), 1, path.name)
                self.assertEqual(audio.getsampwidth(), 2, path.name)
                frames = audio.readframes(audio.getnframes())
            samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
            peak = max(abs(value) for value in samples)
            peak_dbfs = 20 * math.log10(peak / 32768)
            self.assertLessEqual(peak_dbfs, -1.5, path.name)
            self.assertGreater(peak_dbfs, -12, path.name)
            self.assertEqual(sum(abs(value) >= 32767 for value in samples), 0, path.name)

    def test_scripted_audio_references_exist(self) -> None:
        script = (MISSION_SOURCE / "jizan-corridor.lua").read_text(encoding="utf-8")
        references = set(re.findall(r'"(redsea-jizan-[a-z-]+\.wav)"', script))
        self.assertEqual(len(references), 8)
        for filename in references:
            self.assertTrue((BITS / filename).is_file(), filename)

        hodeidah_script = (HODEIDAH_SOURCE / "hodeidah-lifeline.lua").read_text(encoding="utf-8")
        hodeidah_references = set(re.findall(r'"(redsea-hodeidah-[a-z-]+\.wav)"', hodeidah_script))
        self.assertEqual(len(hodeidah_references), 8)
        for filename in hodeidah_references:
            self.assertTrue((BITS / filename).is_file(), filename)

        mandab_script = (MANDAB_SOURCE / "bab-al-mandab-passage.lua").read_text(encoding="utf-8")
        mandab_references = set(re.findall(r'"(redsea-mandab-[a-z-]+\.wav)"', mandab_script))
        self.assertEqual(len(mandab_references), 10)
        for filename in mandab_references:
            self.assertTrue((BITS / filename).is_file(), filename)

    def test_voice_provenance_is_bilingual_and_disclosed(self) -> None:
        provenance = json.loads((ROOT / "assets" / "red-sea-2026" / "voice-provenance.json").read_text(encoding="utf-8"))
        languages = {line["language"] for line in provenance["lines"]}
        self.assertTrue({"en-US", "ar-SA", "ar-YE"}.issubset(languages))
        self.assertTrue(all(line["synthetic_voice_disclosed"] for line in provenance["lines"]))

        mandab = json.loads((ROOT / "assets" / "red-sea-2026" / "mandab-voice-provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(mandab["mission"], "bab-al-mandab-passage-2026")
        self.assertEqual(len(mandab["lines"]), 10)
        self.assertEqual({line["language"] for line in mandab["lines"]}, {"ar-SA", "en-US"})
        self.assertTrue(all(line["synthetic_voice_disclosed"] for line in mandab["lines"]))
        self.assertTrue(all(not line["real_person_imitation"] for line in mandab["lines"]))

    def test_mission_package_is_deterministic_and_scripted(self) -> None:
        required = {"map.yaml", "map.bin", "map.png", "rules.yaml", "map.ftl", "jizan-corridor.lua", "red-sea-mission-manifest.json"}
        with zipfile.ZipFile(MISSION_PACKAGE) as mission:
            self.assertTrue(required.issubset(mission.namelist()))
            self.assertTrue(all(info.date_time == (2026, 8, 11, 0, 0, 0) for info in mission.infolist()))
            map_yaml = mission.read("map.yaml").decode("utf-8")
            rules = mission.read("rules.yaml").decode("utf-8").replace("\r\n", "\n")
            script = mission.read("jizan-corridor.lua").decode("utf-8")
        self.assertIn("Visibility: MissionSelector", map_yaml)
        self.assertIn("Title: 01: Jizan Corridor", map_yaml)
        self.assertIn("Faction: saudi", map_yaml)
        self.assertIn("Faction: yemen", map_yaml)
        self.assertIn("SaudiConyard: fact", map_yaml)
        self.assertIn("SaudiRefinery: proc", map_yaml)
        self.assertIn("jizan-corridor.lua", rules)
        self.assertIn("E7.noautotarget:\n\t-Buildable:", rules)
        for mechanic in ("RestoreRadarObjective", "DestroyLaunchersObjective", "EscortConvoyObjective", "ProtectInfrastructureObjective"):
            self.assertIn(mechanic, script)
        self.assertIn("GuardLauncher(WestGuard1, LauncherWest)", script)
        self.assertIn("GuardLauncher(EastGuard1, LauncherEast)", script)
        self.assertNotIn("Utils.Do({ WestGuard1, WestGuard2, EastGuard1, EastGuard2 }, HuntOnIdle)", script)

    def test_hodeidah_is_a_packaged_playable_yemen_mission(self) -> None:
        required = {
            "map.yaml",
            "map.bin",
            "map.png",
            "rules.yaml",
            "map.ftl",
            "hodeidah-lifeline.lua",
            "red-sea-mission-manifest.json",
        }
        with zipfile.ZipFile(HODEIDAH_PACKAGE) as mission:
            self.assertTrue(required.issubset(mission.namelist()))
            self.assertTrue(all(info.date_time == (2026, 8, 11, 0, 0, 0) for info in mission.infolist()))
            map_yaml = mission.read("map.yaml").decode("utf-8")
            rules = mission.read("rules.yaml").decode("utf-8").replace("\r\n", "\n")
            script = mission.read("hodeidah-lifeline.lua").decode("utf-8")
            manifest = json.loads(mission.read("red-sea-mission-manifest.json"))
        self.assertIn("Title: 02: Hodeidah Lifeline", map_yaml)
        self.assertIn("Playable: True", map_yaml)
        self.assertIn("Faction: yemen", map_yaml)
        for actor in (
            "YemenConyard: fact",
            "YemenWarFactory: weap",
            "YemenAirfield: afld",
            "YemenTechCenter: stek",
            "DroneOne: samad",
            "YemenRifle1: ymr",
            "YemenRocket1: yrpg",
            "YemenDroneSpotter: yspot",
        ):
            self.assertIn(actor, map_yaml)
        self.assertIn("hodeidah-lifeline.lua", rules)
        for mechanic in (
            "ProtectInfrastructureObjective",
            "DeliverReliefObjective",
            "DisperseObjective",
            "EvacuationObjective",
            "EvaluateSurveillanceSweep",
            "StartReliefConvoy",
            "StartEvacuationConvoy",
        ):
            self.assertIn(mechanic, script)
        self.assertEqual(manifest["id"], "hodeidah-lifeline-2026")
        self.assertEqual(len(manifest["features"]), 8)

    def test_red_sea_missions_have_a_dedicated_campaign_group(self) -> None:
        missions = (ROOT / "engine" / "openra" / "mods" / "ra" / "missions.yaml").read_text(encoding="utf-8")
        lines = missions.splitlines()
        campaign_start = lines.index("World War III:") + 1
        campaign = []
        for line in lines[campaign_start:]:
            if not line.startswith("\t"):
                break
            campaign.append(line)
        self.assertEqual(
            [
                "jizan-corridor-2026",
                "hodeidah-lifeline-2026",
                "straits-shield-2026",
                "haitan-network-2026",
                "bab-al-mandab-passage-2026",
            ],
            [line.strip() for line in campaign if line.strip()],
        )

    def test_mandab_is_a_deterministic_registered_playable_mission(self) -> None:
        required = {
            "map.yaml", "map.bin", "map.png", "rules.yaml", "map.ftl",
            "bab-al-mandab-passage.lua", "briefing.md", "red-sea-mission-manifest.json",
        }
        with zipfile.ZipFile(MANDAB_PACKAGE) as mission:
            self.assertTrue(required.issubset(mission.namelist()))
            self.assertTrue(all(info.date_time == (2026, 8, 11, 0, 0, 0) for info in mission.infolist()))
            files = {name: mission.read(name) for name in mission.namelist()}
            manifest = json.loads(files["red-sea-mission-manifest.json"])
        self.assertEqual(manifest["id"], "bab-al-mandab-passage-2026")
        self.assertEqual(manifest["factual_cutoff"], "2026-08-11")
        self.assertEqual(len(manifest["features"]), 7)
        for name, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), digest, name)

        map_yaml = files["map.yaml"].decode("utf-8")
        self.assertIn("Title: Red Sea 2026: Bab al-Mandab Passage", map_yaml)
        self.assertIn("Playable: True", map_yaml)
        self.assertIn("Faction: saudi", map_yaml)
        self.assertIn("SaudiConyard: fact", map_yaml)
        self.assertIn("SaudiRefinery: proc", map_yaml)
        self.assertIn("SaudiWarFactory: weap", map_yaml)
        registry = (ENGINE_ROOT / "mods" / "ra" / "missions.yaml").read_text(encoding="utf-8")
        self.assertIn("\tbab-al-mandab-passage-2026", registry)

    def test_mandab_has_five_linked_objectives_and_every_failure_path(self) -> None:
        script = (MANDAB_SOURCE / "bab-al-mandab-passage.lua").read_text(encoding="utf-8")
        for mechanic in (
            "ReadinessObjective", "ReconObjective", "ThreatObjective", "ShippingObjective", "HoldObjective",
            "ActivateRecon", "ActivateThreatPhase", "StartCivilianShipping", "StartFinalEscalation",
            "FailReadiness", "FailRecon", "FailThreats", "FailShipping", "FailPassage",
        ):
            self.assertIn(mechanic, script)
        self.assertIn('Saudi.HasPrerequisites({ "atek" })', script)
        self.assertIn("SaudiRosterCount() >= 3", script)
        self.assertIn("ReplacementShipsRemaining", script)
        self.assertIn("state.actor.Teleport(state.path[state.step])", script)
        self.assertIn("leadStep - state.step >= 2", script)
        self.assertIn("MANDAB_TEST_PATH = \"live\"", script)
        for path in ("fail-readiness", "fail-recon", "fail-threats", "fail-shipping", "fail-passage"):
            self.assertIn(f'MANDAB_TEST_PATH == "{path}"', script)

    def test_mandab_convoy_waypoints_are_distinct_navigable_water_cells(self) -> None:
        map_yaml = (MANDAB_SOURCE / "map.yaml").read_text(encoding="utf-8")
        names = re.findall(r"\t(Ship(?:Entry|West|Inner|East)[A-Za-z]+): waypoint\n\t\tLocation: (\d+),(\d+)", map_yaml)
        self.assertEqual(len(names), 24)
        locations = [(int(x), int(y)) for _, x, y in names]
        self.assertEqual(len(locations), len(set(locations)))

        binary = (MANDAB_SOURCE / "map.bin").read_bytes()
        _, width, height, tiles_offset, _, _ = struct.unpack("<BHHIII", binary[:17])
        self.assertEqual((width, height), (96, 96))
        for x, y in locations:
            offset = tiles_offset + 3 * (x * height + y)
            template = struct.unpack("<H", binary[offset:offset + 2])[0]
            self.assertEqual(template, 256, f"ship waypoint {x},{y} must be open water")

    def test_mandab_source_boundary_and_unicode_subtitles_are_explicit(self) -> None:
        briefing = (MANDAB_SOURCE / "briefing.md").read_text(encoding="utf-8")
        fluent = (MANDAB_SOURCE / "map.ftl").read_text(encoding="utf-8")
        self.assertIn("Factual cutoff: **11 August 2026**", briefing)
        self.assertIn("## Sourced background", briefing)
        self.assertIn("## Fictional mission situation", briefing)
        for authority in ("International Maritime Organization", "Energy Information Administration", "UNCTAD"):
            self.assertIn(authority, briefing)
        for text in ("قيادة الممر", "العبور المدني", "اكتمل العبور"):
            self.assertIn(text, fluent)


if __name__ == "__main__":
    unittest.main()
