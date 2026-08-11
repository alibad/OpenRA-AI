from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SourceReference:
    title: str
    publisher: str
    published: str
    url: str


@dataclass(frozen=True)
class FactionProfile:
    id: str
    name: str
    openra_side: str
    doctrine: str
    strengths: tuple[str, ...]
    constraints: tuple[str, ...]
    signature_units: tuple[str, ...]


@dataclass(frozen=True)
class MissionBlueprint:
    id: str
    title: str
    region: str
    factual_cutoff: str
    player_faction: str
    opponent_faction: str
    situation: str
    objectives: tuple[str, ...]
    mechanics: tuple[str, ...]
    sources: tuple[SourceReference, ...]

    def as_dict(self) -> dict:
        return asdict(self)


FACTIONS = {
    "saudi": FactionProfile(
        id="saudi",
        name="Saudi Arabia",
        openra_side="Allies",
        doctrine="Networked defense and logistics",
        strengths=("layered air defense", "armored counterattack", "rapid reinforcement"),
        constraints=("high unit cost", "depends on radar and supply infrastructure"),
        signature_units=("M1A2S", "Mobile Air Defense System", "Airborne Radar"),
    ),
    "yemen": FactionProfile(
        id="yemen",
        name="Yemen",
        openra_side="Soviet",
        doctrine="Dispersed coastal defense and mobile strike",
        strengths=("concealment", "mobile launchers", "low-cost drone pressure"),
        constraints=("limited heavy armor", "fragile fixed infrastructure"),
        signature_units=("Armed Technical", "Samad Drone", "Mobile Missile Launcher"),
    ),
}


MISSIONS = {
    "jizan-corridor-2026": MissionBlueprint(
        id="jizan-corridor-2026",
        title="Jizan Corridor",
        region="Jizan and the southern Red Sea approaches",
        factual_cutoff="2026-08-11",
        player_faction="saudi",
        opponent_faction="yemen",
        situation=(
            "A source-dated strategy scenario about maintaining radar coverage, protecting "
            "civilian navigation, and locating mobile launch systems during a regional escalation."
        ),
        objectives=(
            "Restore the coastal radar and layered air-defense network.",
            "Escort the civilian and supply convoy through the marked corridor.",
            "Use reconnaissance to locate mobile launch systems.",
            "Keep the port and desalination infrastructure operational.",
        ),
        mechanics=("drone warfare", "layered air defense", "convoy logistics"),
        sources=(
            SourceReference(
                title="Statement on renewed threats to maritime navigation in the Red Sea",
                publisher="United Nations Office of the Special Envoy for Yemen",
                published="2026-07-24",
                url=(
                    "https://osesgy.unmissions.org/en/news/statement-attributable-to-the-"
                    "spokesperson-for-the-secretary-general-on-the-renewed"
                ),
            ),
            SourceReference(
                title="Three drones intercepted after entering Saudi airspace",
                publisher="Saudi Press Agency",
                published="2026-05-17",
                url="https://www.spa.gov.sa/en/N2588234",
            ),
        ),
    ),
    "hodeidah-lifeline-2026": MissionBlueprint(
        id="hodeidah-lifeline-2026",
        title="Hodeidah Lifeline",
        region="Hodeidah and the eastern Red Sea coast",
        factual_cutoff="2026-08-11",
        player_faction="yemen",
        opponent_faction="saudi",
        situation=(
            "A source-dated strategy scenario about keeping a coastal aid and fisheries corridor "
            "operational while fixed infrastructure and dispersed forces face sustained pressure."
        ),
        objectives=(
            "Protect the port, fisheries depot, and marked civilian infrastructure.",
            "Move relief supplies to the inland distribution point.",
            "Disperse mobile forces before each surveillance sweep.",
            "Preserve an evacuation route until the final convoy departs.",
        ),
        mechanics=("concealment", "mobile strike", "convoy logistics"),
        sources=(
            SourceReference(
                title="Yemen Fisheries Market Systems Analysis Report",
                publisher="United Nations Development Programme",
                published="2026-06-28",
                url="https://www.undp.org/yemen/publications/yemen-fisheries-market-systems-analysis-report",
            ),
            SourceReference(
                title="Statement on renewed threats to maritime navigation in the Red Sea",
                publisher="United Nations Office of the Special Envoy for Yemen",
                published="2026-07-24",
                url=(
                    "https://osesgy.unmissions.org/en/news/statement-attributable-to-the-"
                    "spokesperson-for-the-secretary-general-on-the-renewed"
                ),
            ),
        ),
    ),
}


def mission_blueprint(scenario_id: str) -> MissionBlueprint | None:
    if not scenario_id:
        return None
    return MISSIONS.get(scenario_id)


def scenario_manifest(scenario_id: str) -> dict | None:
    blueprint = mission_blueprint(scenario_id)
    if blueprint is None:
        return None

    value = blueprint.as_dict()
    value["factions"] = {
        faction_id: asdict(FACTIONS[faction_id])
        for faction_id in (blueprint.player_faction, blueprint.opponent_faction)
    }
    value["editorial_boundary"] = (
        "The background is source-dated. Objectives, force composition, timing, distances, and "
        "outcomes are authored gameplay abstractions and are not claims about an exact operation."
    )
    return value
