"""Contact sheets for ``modern_faction_art_audit.py``.

Frames are composited the way the renderer draws them: each frame canvas is
centred on the actor pivot, turrets are seated at the ``Turreted.Offset``
projected for the quantized body facing, index 0 is transparent, index 4 is
the translucent unit shadow, and indices 80..95 are remapped with OpenRA's
player-colour algorithm.  Unit art in Red Alert always uses the temperate
``player`` palette; the snow and desert rows change the terrain underneath,
which is what changes contrast in a real match.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from modern_faction_art_audit import (
    ROLE_PAIRS,
    TERRAIN_PALETTES,
    TERRAIN_TILES,
    TILESETS,
    load_pal,
    player_palette,
    turret_screen_offset,
)

if TYPE_CHECKING:
    from modern_faction_art_audit import ActorRecord, Audit, SequenceSpec


PLAYER_COLOURS = {"blue": (59, 105, 229), "red": (214, 45, 38)}
LABEL = (235, 235, 220, 255)
BACKDROP = (28, 30, 34, 255)
FONT = ImageFont.load_default()


class Painter:
    def __init__(self, audit: "Audit") -> None:
        self.audit = audit
        engine = audit.engine
        base = load_pal(engine.locate("temperat.pal")[0], transparent=(0,), shadow=(4,))
        self.unit_palettes = {name: player_palette(base, colour) for name, colour in PLAYER_COLOURS.items()}
        self.chrome_palette = load_pal(engine.locate("temperat.pal")[0], transparent=(0,), shadow=(3,))
        self.terrain: dict[str, np.ndarray] = {}
        for tileset in TILESETS:
            palette = load_pal(engine.locate(TERRAIN_PALETTES[tileset])[0], transparent=(), shadow=(3, 4))
            try:
                frames, _ = engine.frames(TERRAIN_TILES[tileset])
            except (FileNotFoundError, RuntimeError):
                frames = []
            tiles = [palette[f] for f in frames if f.shape == (24, 24)] or [np.full((24, 24, 4), (90, 110, 70, 255), np.uint8)]
            self.terrain[tileset] = tiles

    def background(self, tileset: str, width: int, height: int) -> Image.Image:
        tiles = self.terrain[tileset]
        canvas = np.zeros((height, width, 4), dtype=np.uint8)
        for ty in range(0, height, 24):
            for tx in range(0, width, 24):
                tile = tiles[((tx // 24) * 7 + (ty // 24) * 3) % len(tiles)]
                h = min(24, height - ty)
                w = min(24, width - tx)
                canvas[ty: ty + h, tx: tx + w] = tile[:h, :w]
        return Image.fromarray(canvas, "RGBA")

    @staticmethod
    def colour(frame: np.ndarray, palette: np.ndarray) -> Image.Image:
        return Image.fromarray(palette[frame], "RGBA")

    def composite(self, record: "ActorRecord", facing: int, colour: str, cell: tuple[int, int], tileset: str | None = "TEMPERAT",
                  turret_facing: int | None = None, sequence: str | None = None, frame: int = 0) -> Image.Image:
        """Render one actor pose centred in a cell."""

        sequence = sequence or body_sequence(self.audit, record)
        width, height = cell
        base = self.background(tileset, width, height) if tileset else Image.new("RGBA", cell, BACKDROP)
        palette = self.unit_palettes[colour]
        body = self.audit.sequence(record.image, sequence)
        if body is None:
            return base
        body_frames = self.audit.sequence_frames(body, tileset or "TEMPERAT")
        if not body_frames:
            return base
        facing_index = facing % len(body_frames)
        group = body_frames[facing_index]
        image = self.colour(group[frame % len(group)], palette)
        cx, cy = width // 2, height // 2
        base.alpha_composite(image, (cx - image.width // 2, cy - image.height // 2))
        turret = self.audit.sequence(record.image, "turret")
        if sequence == "idle" and turret is not None and record.turrets:
            turret_frames = self.audit.sequence_frames(turret, tileset or "TEMPERAT")
            if turret_frames:
                body_angle = body.facing_angle(facing_index)
                if turret_facing is None:
                    # Point the turret along the hull: pick the turret frame for the same world angle.
                    turret_index = nearest_facing(turret, body_angle)
                else:
                    turret_index = turret_facing % len(turret_frames)
                dx, dy = turret_screen_offset(next(iter(record.turrets.values())), body_angle)
                timage = self.colour(turret_frames[turret_index][0], palette)
                base.alpha_composite(timage, (int(round(cx + dx)) - timage.width // 2, int(round(cy + dy)) - timage.height // 2))
        return base


def body_sequence(audit: "Audit", record: "ActorRecord") -> str:
    """The resting body sequence: ``idle`` for vehicles/aircraft/ships/buildings, ``stand`` for infantry."""

    sequences = audit.sequences.get(record.image, {})
    for name in ("idle", "stand"):
        if name in sequences:
            return name
    return "idle"


def nearest_facing(spec: "SequenceSpec", angle: int) -> int:
    best = 0
    best_delta = 4096
    for index in range(spec.facings):
        delta = abs((spec.facing_angle(index) - angle + 512) % 1024 - 512)
        if delta < best_delta:
            best, best_delta = index, delta
    return best


def label(image: Image.Image, text: str, xy: tuple[int, int]) -> None:
    draw = ImageDraw.Draw(image)
    draw.rectangle((xy[0], xy[1], xy[0] + 6 * len(text) + 4, xy[1] + 11), fill=(0, 0, 0, 170))
    draw.text((xy[0] + 2, xy[1]), text, font=FONT, fill=LABEL)


def cell_size(audit: "Audit", record: "ActorRecord") -> tuple[int, int]:
    size = [24, 24]
    for spec in audit.sequences.get(record.image, {}).values():
        frames = audit.sequence_frames(spec)
        if frames and frames[0]:
            h, w = frames[0][0].shape
            size[0] = max(size[0], w)
            size[1] = max(size[1], h)
    return (min(size[0] + 8, 160), min(size[1] + 8, 160))


def stack(rows: list[Image.Image], title: str) -> Image.Image:
    width = max(row.width for row in rows) if rows else 200
    height = sum(row.height + 4 for row in rows) + 16
    sheet = Image.new("RGBA", (max(width, 6 * len(title) + 8), height), BACKDROP)
    label(sheet, title, (2, 2))
    y = 16
    for row in rows:
        sheet.alpha_composite(row, (0, y))
        y += row.height + 4
    return sheet


def strip(cells: list[Image.Image], caption: str) -> Image.Image:
    if not cells:
        return Image.new("RGBA", (10, 10), BACKDROP)
    width = sum(c.width for c in cells)
    height = max(c.height for c in cells) + 12
    row = Image.new("RGBA", (max(width, 6 * len(caption) + 8), height), BACKDROP)
    label(row, caption, (0, 0))
    x = 0
    for cell in cells:
        row.alpha_composite(cell, (x, 12))
        x += cell.width
    return row


def wrap(cells: list[Image.Image], per_row: int) -> list[list[Image.Image]]:
    return [cells[i: i + per_row] for i in range(0, len(cells), per_row)]


def actor_sheet(painter: Painter, record: "ActorRecord", native: "ActorRecord | None") -> Image.Image:
    audit = painter.audit
    cell = cell_size(audit, record)
    rows: list[Image.Image] = []
    body = audit.sequence(record.image, body_sequence(audit, record))
    facings = body.facings if body else 1
    # 1. Every body facing, turret aligned, temperate/blue.
    cells = [painter.composite(record, f, "blue", cell) for f in range(facings)]
    for index, chunk in enumerate(wrap(cells, 16)):
        rows.append(strip(chunk, f"idle facings {index * 16}..{index * 16 + len(chunk) - 1} (turret aligned)"))
    # 2. Turret locked while the hull rotates (seat/pivot check).
    turret = audit.sequence(record.image, "turret")
    if turret is not None and record.turrets and body is not None:
        cells = [painter.composite(record, f, "blue", cell, turret_facing=0) for f in range(facings)]
        for index, chunk in enumerate(wrap(cells, 16)):
            rows.append(strip(chunk, f"hull rotating, turret frame 0 ({index})"))
        turret_frames = audit.sequence_frames(turret)
        if turret_frames:
            tcells = []
            for group in turret_frames:
                base = Image.new("RGBA", cell, (60, 70, 60, 255))
                timage = painter.colour(group[0], painter.unit_palettes["blue"])
                base.alpha_composite(timage, (cell[0] // 2 - timage.width // 2, cell[1] // 2 - timage.height // 2))
                ImageDraw.Draw(base).point((cell[0] // 2, cell[1] // 2), fill=(255, 0, 255, 255))
                tcells.append(base)
            for index, chunk in enumerate(wrap(tcells, 16)):
                rows.append(strip(chunk, f"turret alone, magenta = canvas pivot ({index})"))
    # 3. Other sequences (facing 0 animation frames, then facings of directional ones).
    for name, spec in sorted(audit.sequences.get(record.image, {}).items()):
        if name in ("idle", "turret", "icon", body_sequence(audit, record)):
            continue
        frames = audit.sequence_frames(spec)
        if not frames:
            continue
        cells = []
        for frame_index in range(min(len(frames[0]), 16)):
            cells.append(painter.composite(record, 0, "blue", cell, sequence=name, frame=frame_index))
        if spec.facings > 1 and len(frames[0]) == 1:
            cells = [painter.composite(record, f, "blue", cell, sequence=name) for f in range(min(spec.facings, 32))]
        for index, chunk in enumerate(wrap(cells, 16)):
            rows.append(strip(chunk, f"{name} ({spec.facings}f x {len(frames[0])})"))
    # 4. Terrain x player colour matrix at eight compass facings.
    step = max(1, facings // 8)
    for tileset in TILESETS:
        for colour in PLAYER_COLOURS:
            cells = [painter.composite(record, i * step, colour, cell, tileset=tileset) for i in range(min(8, facings))]
            if native is not None:
                native_body = audit.sequence(native.image, body_sequence(audit, native))
                nfacings = native_body.facings if native_body else 1
                nstep = max(1, nfacings // 8)
                ncell = cell_size(audit, native)
                cells.append(Image.new("RGBA", (6, cell[1]), BACKDROP))
                cells += [painter.composite(native, i * nstep, colour, (ncell[0], cell[1]), tileset=tileset) for i in range(min(8, nfacings))]
            rows.append(strip(cells, f"{tileset.lower()} / {colour}" + (f"  | native {native.name}" if native else "")))
    # 5. Production icon beside the native reference icon.
    icon_cells = []
    for subject in [record, native]:
        if subject is None:
            continue
        icon = audit.sequence(subject.image, "icon")
        frames = audit.sequence_frames(icon) if icon else None
        if frames:
            icon_cells.append(painter.colour(frames[0][0], painter.chrome_palette))
            icon_cells.append(Image.new("RGBA", (6, 48), BACKDROP))
    if icon_cells:
        rows.append(strip(icon_cells, "icon | native icon"))
    return stack(rows, f"{record.name} ({record.image}) {record.faction} {record.domain}")


def roster_sheet(painter: Painter, faction: str, domain_actors: dict[str, list[str]]) -> Image.Image:
    audit = painter.audit
    rows = []
    for domain, actors in domain_actors.items():
        for actor in actors:
            record = audit.actors.get(actor)
            if record is None:
                continue
            body = audit.sequence(record.image, body_sequence(audit, record))
            facings = body.facings if body else 1
            step = max(1, facings // 8)
            cell = cell_size(audit, record)
            cells = [painter.composite(record, i * step, "red", cell) for i in range(min(8, facings))]
            native_name = ROLE_PAIRS.get(actor)
            native = audit.natives.get(native_name) if native_name else None
            if native is not None:
                nbody = audit.sequence(native.image, body_sequence(audit, native))
                nfacings = nbody.facings if nbody else 1
                ncell = cell_size(audit, native)
                cells.append(Image.new("RGBA", (6, cell[1]), BACKDROP))
                cells += [painter.composite(native, i * max(1, nfacings // 8), "red", (ncell[0], cell[1]))
                          for i in range(min(8, nfacings))]
            rows.append(strip(cells, f"{domain}: {actor}" + (f" vs native {native_name}" if native else "")))
    return stack(rows, f"{faction} roster, temperate, red player, eight compass facings")


def icon_sheet(painter: Painter, faction: str, domain_actors: dict[str, list[str]]) -> Image.Image:
    audit = painter.audit
    cells = []
    for actors in domain_actors.values():
        for actor in actors:
            record = audit.actors.get(actor)
            if record is None:
                continue
            icon = audit.sequence(record.image, "icon")
            frames = audit.sequence_frames(icon) if icon else None
            if not frames:
                continue
            tile = Image.new("RGBA", (70, 64), BACKDROP)
            tile.alpha_composite(painter.colour(frames[0][0], painter.chrome_palette), (3, 3))
            label(tile, actor[:11], (0, 52))
            cells.append(tile)
    rows = [strip(chunk, "") for chunk in wrap(cells, 8)]
    return stack(rows, f"{faction} production icons (chrome palette)")


def review_sheet(painter: Painter, record: "ActorRecord", native: "ActorRecord | None") -> Image.Image:
    """Eight compass facings per player colour beside the role-paired native unit (for 4x review)."""

    audit = painter.audit
    body = audit.sequence(record.image, body_sequence(audit, record))
    facings = body.facings if body else 1
    step = max(1, facings // 8)
    cell = cell_size(audit, record)
    rows = []
    for tileset, colour in (("TEMPERAT", "blue"), ("SNOW", "red"), ("DESERT", "blue")):
        rows.append(strip([painter.composite(record, i * step, colour, cell, tileset=tileset) for i in range(min(8, facings))],
                          f"{record.name} {tileset.lower()}/{colour}"))
    if native is not None:
        nbody = audit.sequence(native.image, body_sequence(audit, native))
        nfacings = nbody.facings if nbody else 1
        ncell = cell_size(audit, native)
        rows.append(strip([painter.composite(native, i * max(1, nfacings // 8), "blue", (max(ncell[0], cell[0]), max(ncell[1], cell[1])))
                           for i in range(min(8, nfacings))], f"native {native.name} temperate/blue"))
    return stack(rows, f"{record.name} review")


def save(image: Image.Image, path: Path, scales: tuple[int, ...] = (1, 2)) -> list[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for scale in scales:
        target = path.with_name(f"{path.stem}-{scale}x.png")
        scaled = image if scale == 1 else image.resize((image.width * scale, image.height * scale), Image.NEAREST)
        scaled.convert("RGB").save(target)
        written.append(str(target))
    return written


def render_all(audit: "Audit", output: Path) -> dict[str, Any]:
    painter = Painter(audit)
    written: dict[str, Any] = {"actors": {}, "factions": {}}
    for name, record in sorted(audit.actors.items()):
        native_name = ROLE_PAIRS.get(name)
        native = audit.natives.get(native_name) if native_name else None
        faction = record.faction.split(",")[0]
        sheet = actor_sheet(painter, record, native)
        stem = name.lower().replace(".", "_")
        written["actors"][name] = save(sheet, output / faction / stem)
        if record.parent is None and not record.stock:
            written["actors"][name] += save(review_sheet(painter, record, native), output / faction / f"{stem}-review", scales=(4,))
    for faction in audit.factions:
        roster = audit.catalog[faction]["roster"]
        written["factions"][faction] = {
            "roster": save(roster_sheet(painter, faction, roster), output / faction / "_roster", scales=(2,)),
            "icons": save(icon_sheet(painter, faction, roster), output / faction / "_icons", scales=(2,)),
        }
    previews = []
    for faction, info in getattr(audit, "previews", {}).items():
        image = Image.open(audit.engine.root / info["path"]).convert("RGBA")
        tile = Image.new("RGBA", (image.width, image.height + 14), BACKDROP)
        tile.alpha_composite(image, (0, 14))
        label(tile, f"{faction} {info['size'][0]}x{info['size'][1]}", (0, 0))
        previews.append(tile)
    if previews:
        rows = [strip(chunk, "") for chunk in wrap(previews, 3)]
        written["previews"] = save(stack(rows, "Faction previews"), output / "_previews", scales=(1,))
    (output / "index.json").write_text(__import__("json").dumps(written, indent=2), encoding="utf-8")
    return written
