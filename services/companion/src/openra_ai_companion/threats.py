from __future__ import annotations

from math import hypot

from .models import GameSnapshot, ThreatAssessment, Unit


def _nearest_distance(enemies: tuple[Unit, ...], assets: tuple[Unit, ...]) -> float | None:
    if not enemies or not assets:
        return None
    return min(
        hypot(enemy.cell_x - asset.cell_x, enemy.cell_y - asset.cell_y)
        for enemy in enemies
        for asset in assets
    )


def assess_threat(snapshot: GameSnapshot) -> ThreatAssessment:
    """Score immediate risk using only the player's fog-respecting snapshot."""
    if snapshot.done:
        return ThreatAssessment(0, "calm", "Match complete")

    mission_spies = [
        unit for unit in snapshot.units
        if unit.can_disguise or unit.can_infiltrate or unit.kind.lower().split(".", 1)[0] == "spy"
    ]
    if snapshot.mission_mode and mission_spies:
        detectors = [
            enemy for enemy in snapshot.visible_enemies
            if enemy.detects_disguise or enemy.kind.lower().split(".", 1)[0] == "dog"
        ]
        exposed_spies = [spy for spy in mission_spies if not spy.is_disguised]
        threats = snapshot.visible_enemies if exposed_spies else tuple(detectors)
        watched = tuple(exposed_spies or mission_spies)
        distance = _nearest_distance(tuple(threats), watched)
        if distance is None:
            return ThreatAssessment(5 if detectors else 0, "calm", "Stealth route clear of visible dog detectors")
        if distance <= 5:
            score = 100
        elif distance <= 9:
            score = 70
        elif distance <= 14:
            score = 40
        else:
            score = 15
        level = "critical" if score >= 70 else "high" if score >= 45 else "guarded" if score >= 20 else "calm"
        source = "enemy contact" if exposed_spies else "dog detector"
        return ThreatAssessment(score, level, f"Nearest {source} is {round(distance)} cells from the Spy")

    enemies = snapshot.visible_enemies
    score = 0
    reasons: list[str] = []

    if enemies:
        score += 8 + min(28, 4 * len(enemies))
        reasons.append(f"{len(enemies)} visible enemy unit{'s' if len(enemies) != 1 else ''}")

        protected_assets = snapshot.buildings or snapshot.units
        distance = _nearest_distance(enemies, protected_assets)
        if distance is not None:
            if distance <= 6:
                score += 46
            elif distance <= 12:
                score += 34
            elif distance <= 20:
                score += 22
            elif distance <= 32:
                score += 10
            reasons.append(f"nearest contact {round(distance)} cells away")

        defenders = sum(1 for unit in snapshot.units if unit.can_attack)
        if defenders == 0:
            score += 12
        elif len(enemies) >= max(3, defenders * 2):
            score += 10

    if snapshot.visible_enemy_buildings:
        score += min(10, 2 * len(snapshot.visible_enemy_buildings))
        if not reasons:
            reasons.append("visible enemy structures")

    low_power = snapshot.power_drained > snapshot.power_provided
    critical_assets = [asset for asset in (*snapshot.units, *snapshot.buildings) if asset.hp_percent <= 0.22]
    if low_power and enemies:
        score += 6
        reasons.append("low power")
    if critical_assets:
        score += 12 if not enemies else 8
        reasons.append("critically damaged assets")

    score = min(100, score)
    if score >= 70:
        level = "critical"
    elif score >= 45:
        level = "high"
    elif score >= 20:
        level = "guarded"
    else:
        level = "calm"

    reason = "; ".join(dict.fromkeys(reasons[:2])) or "No immediate visible threat"
    return ThreatAssessment(score, level, reason)
