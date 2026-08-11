from __future__ import annotations

import unittest

from openra_ai_companion.mission_eval import inventory_missions


class MissionCorpusEvalTests(unittest.TestCase):
    def test_every_declared_red_alert_mission_is_inventoried(self) -> None:
        missions = inventory_missions()

        self.assertEqual(len(missions), 62)
        self.assertTrue(all(mission.available for mission in missions))
        self.assertEqual(len({mission.map_name for mission in missions}), 62)

    def test_required_human_slots_are_detected_from_each_map(self) -> None:
        missions = {mission.map_name: mission for mission in inventory_missions()}

        self.assertEqual(missions["allies-01"].player_slot, "Greece")
        self.assertEqual(missions["soviet-01"].player_slot, "USSR")
        self.assertEqual(missions["evacuation"].player_slot, "Allies1")
        self.assertEqual(missions["ant-01"].player_slot, "Spain")

    def test_generated_red_sea_mission_uses_installable_package_name(self) -> None:
        missions = {item.map_name: item for item in inventory_missions()}
        mission = missions["jizan-corridor-2026"]

        self.assertEqual(mission.request_name, "jizan-corridor-2026.oramap")
        self.assertEqual(mission.player_slot, "Saudi Arabia")
        self.assertEqual(missions["hodeidah-lifeline-2026"].request_name, "hodeidah-lifeline-2026.oramap")
        self.assertEqual(missions["hodeidah-lifeline-2026"].player_slot, "Yemen")


if __name__ == "__main__":
    unittest.main()
