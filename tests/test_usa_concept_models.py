"""Contract checks for the United States Checkpoint B concept renderer."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import usa_concept_actors as actors  # noqa: E402
import usa_concept_models as models  # noqa: E402
import usa_concept_render as board_render  # noqa: E402


# faction-spec-usa.md §3: 4 infantry, 6 vehicles, 4 aircraft, 3 ships, USTOC and 3 defenses.
CONTRACT_ROSTER = (
	"USRIFLE", "USJAV", "USJTAC", "TALONSIX",
	"USMBT", "USIFV", "USICV", "USHIMARS", "USSHORAD", "USRECOV",
	"USF35", "USMQ9", "USUH60", "USAC130",
	"USDDG", "USSSN", "USLPD",
	"USTOC", "USIAMD", "USCUAS", "USNODE",
)


def synthetic_palette() -> tuple[tuple[int, int, int], ...]:
	"""A deterministic 256-colour palette with a Red Alert style remap ramp."""

	colors = []
	for index in range(256):
		if 80 <= index <= 95:
			value = 244 - (index - 80) * 13
			colors.append((value, round(value * 0.87), round(value * 0.5)))
		else:
			colors.append(((index * 37) % 256, (index * 91) % 256, (index * 53) % 256))
	return tuple(colors)


PALETTE = models.PaletteMap(synthetic_palette())


def frames(actor: str, state_index: int = 0) -> list[Image.Image]:
	spec = actors.ACTORS[actor]
	return [actors.sprite(spec, spec.states[state_index], yaw, PALETTE) for yaw in spec.yaws()]


def test_registry_is_exactly_the_contract_roster() -> None:
	assert actors.ROSTER == CONTRACT_ROSTER


@pytest.mark.parametrize("actor", CONTRACT_ROSTER)
def test_every_state_renders_distinct_unclipped_facings(actor: str) -> None:
	spec = actors.ACTORS[actor]
	expected = 1 if spec.domain == "structure" else 8
	for state_index, state in enumerate(spec.states):
		rendered = frames(actor, state_index)
		assert len(rendered) == expected
		digests = {hashlib.sha256(frame.tobytes()).hexdigest() for frame in rendered}
		assert len(digests) == expected, f"{actor} {state.name}: duplicated facing"
		for frame in rendered:
			assert frame.mode == "P" and frame.size == spec.frame
			mask = Image.frombytes("L", frame.size, bytes(255 if value not in (0, 4) else 0 for value in frame.tobytes()))
			box = mask.getbbox()
			assert box is not None, f"{actor} {state.name}: empty frame"
			assert box[0] > 0 and box[1] > 0 and box[2] < frame.width and box[3] < frame.height, f"{actor} {state.name}: clips its canvas {box}"


@pytest.mark.parametrize("actor", CONTRACT_ROSTER)
def test_player_colour_is_intentional_and_reserved_indexes_are_unused(actor: str) -> None:
	rendered = frames(actor)
	values = [value for frame in rendered for value in frame.tobytes()]
	used = set(values)
	# Only transparency, the shadow index, the remap ramp, and ordinary colours.
	assert not used & (set(range(1, 4)) | set(range(5, 12)) | set(range(96, 104)))
	share = sum(board_render.remap_share(frame) for frame in rendered) / len(rendered)
	# Every actor carries an authored player-colour zone, and none repeats the
	# shipped M1A2S/ARAS8 problem of remapping most of the sprite.
	assert 0.02 <= share <= 0.35, f"{actor}: remap share {share:.3f}"


def test_state_changes_read_as_silhouette_changes() -> None:
	# Raise/lower, deploy and door states are gameplay telegraphs, so they must
	# change the outline on most facings, not only the colours.  (The F-35 bay
	# doors open under the fuselage and are deliberately excluded; see README.)
	for actor in ("USIFV", "USHIMARS", "USSHORAD", "USRECOV", "USIAMD", "USLPD", "USUH60", "USJAV", "USJTAC", "TALONSIX"):
		spec = actors.ACTORS[actor]
		yaws = spec.yaws()
		changed = 0
		for yaw in yaws:
			outlines = [board_render.silhouette(actors.sprite(spec, state, yaw, PALETTE)).tobytes() for state in spec.states[:2]]
			changed += outlines[0] != outlines[1]
		assert changed * 2 >= len(yaws), f"{actor}: state change visible on {changed}/{len(yaws)} facings"


def test_rendering_is_deterministic() -> None:
	first = [frame.tobytes() for frame in frames("USMBT")]
	second = [frame.tobytes() for frame in frames("USMBT")]
	assert first == second


def test_player_colour_remap_matches_engine_rules() -> None:
	# PlayerColorRemap keeps the original brightness and takes hue/saturation
	# from the player colour; a white player colour therefore yields a grey of
	# the original's brightest channel.
	assert board_render.remap_color((244, 212, 120), (255, 255, 255)) == (244, 244, 244)
	red = board_render.remap_color((244, 212, 120), (245, 6, 6))
	assert red[0] > red[1] and red[0] > red[2]


def test_mandatory_landmarks_exist_in_geometry() -> None:
	# §8.1: the U.S. tank carries APS boxes, a slatted roof screen and a deep
	# bustle rack; §8.3: the carrier has a V-hull and a forward offset RWS.
	turret = actors.usmbt_turret()
	assert any(face.color == models.APS for face in turret.faces)
	assert sum(1 for face in turret.faces if face.color == models.SLAT) >= 5 * 4
	assert max(v[1] for face in turret.faces for v in face.vertices) > 1.7
	hull = actors.usicv_hull()
	assert min(v[2] for face in hull.faces if face.color == models.VHULL for v in face.vertices) < 0.2
	rws = actors.usicv_turret()
	xs = [v[0] for face in rws.faces for v in face.vertices]
	ys = [v[1] for face in rws.faces for v in face.vertices]
	assert sum(xs) / len(xs) > 0.3 and sum(ys) / len(ys) < -0.8
