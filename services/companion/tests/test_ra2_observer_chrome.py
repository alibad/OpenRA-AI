from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RA2ObserverChromeTests(unittest.TestCase):
    def test_observer_shroud_selector_matches_the_engine_widget_contract(self):
        # ObserverShroudSelectorLogic looks up LABEL as a LabelWithTooltipWidget.
        # Upstream RA2's plain Label made the logic fail before binding FLAG,
        # so the first spectator/replay frame crashed with "Sprite `/` was not found".
        patch = (ROOT / "apps/installer/ra2/compatibility.patch").read_text(encoding="utf-8").replace("\r\n", "\n")
        section = patch.split("--- a/mods/ra2/chrome/ingame-observer.yaml\n", 1)[1].split("\n--- a/", 1)[0]
        self.assertIn("-\t\t\t\t\t\tLabel@LABEL:\n+\t\t\t\t\t\tLabelWithTooltip@LABEL:\n", section)
        self.assertIn("+\t\t\t\t\t\t\tTooltipContainer: TOOLTIP_CONTAINER\n", section)
        logic = ROOT / "engine/openra/OpenRA.Mods.Common/Widgets/Logic/Ingame/ObserverShroudSelectorLogic.cs"
        if logic.is_file():
            self.assertIn('Get<LabelWithTooltipWidget>("LABEL")', logic.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
