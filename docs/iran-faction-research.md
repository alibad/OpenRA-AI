# Iran faction research and gameplay translation

Research cutoff: **2026-08-12**. The roster is a fictional, balanced RTS
interpretation of broad military roles. It is not an order of battle, target
study, or recreation of a real operation. No real commander or political
leader appears in the faction, and the build-limit-one hero, **Shadow One**, is
an original fictional character.

## Source record

The sources below are primary government publications or authoritative public
reports. U.S. government descriptions of Iran are written from an adversarial
policy perspective, so they are used only for broad capability categories and
are not treated as neutral claims about intent or effectiveness.

- **Parallel conventional and asymmetric forces — 22 May 2025.** The
  Congressional Research Service describes Iran's regular Artesh and the IRGC
  as parallel forces with their own land, air, and naval components. It assigns
  territorial defense mainly to the Artesh and broader internal and regional
  missions to the IRGC. Source: [CRS R47321, *Iran: Background and U.S.
  Policy*](https://www.congress.gov/crs-product/R47321).
- **Basij reserve scale — 2022 estimate, archived by CIA.** The CIA World
  Factbook archive estimated roughly 90,000 active Basij paramilitary personnel
  in 2022, while noting that Iranian force-strength information varies. This
  supports a numerous low-cost infantry role, not a historical "human wave"
  simulation. Source: [CIA World Factbook 2022 archive, military and security
  service personnel strengths](https://www.cia.gov/the-world-factbook/about/archives/2022/field/military-and-security-service-personnel-strengths/).
- **Missile emphasis — 22 May 2025.** CRS reports that Iran emphasizes the
  accuracy, lethality, and reliability of a large regional ballistic-missile
  inventory. The game translates this into expensive, telegraphed mobile and
  coastal launchers with long reload windows, not strategic-range or nuclear
  weapons. Source: [CRS R47321](https://www.congress.gov/crs-product/R47321).
- **Mohajer UAV production ecosystem — 1 April 2025.** A U.S. Treasury release
  identifies Qods Aviation Industries as a UAV manufacturer and describes
  procurement of components used in the Mohajer-6 combat UAV. Source:
  [U.S. Treasury, "The Departments of Treasury and Justice Take Action Against
  Iranian Weapons Procurement Network"](https://home.treasury.gov/news/press-releases/sb0066).
- **Ababil UAV and domestic aircraft production — 31 July 2025.** U.S.
  Treasury describes HESA as a state-owned manufacturer of military aircraft
  and Ababil-series UAVs. The faction therefore fields separate reconnaissance,
  reusable strike-drone, and expendable loitering-munition roles. Source:
  [U.S. Treasury, "Treasury Sanctions Global Network Supporting Iran's Military
  UAV Program"](https://home.treasury.gov/news/press-releases/sb0217).
- **Radar, surface-to-air missiles, and helicopter sustainment — 1 October
  2025.** U.S. Treasury describes Iranian production of radar and missile
  guidance equipment for surface-to-air defense, and a domestic organization
  that builds and overhauls helicopters. This supports a radar-gated mobile air
  defense vehicle and a maintained attack-helicopter role. Source:
  [U.S. Treasury, "Treasury Targets Iranian Weapons Procurement Networks
  Supporting Ballistic Missile and Military Aircraft Programs"](https://home.treasury.gov/news/press-releases/sb0270).
- **Layered littoral defense — 4 August 2025.** CRS identifies two Iranian naval
  services and describes mines, shore-based anti-ship missiles, fast inshore
  attack craft, warships, and a drone carrier among the broad means available
  for littoral operations. The game uses fast missile boats, a small submarine,
  and a coastal missile truck; it deliberately omits mining civilian shipping.
  Source: [CRS R45281, *Iran Conflict and the Strait of Hormuz: Oil and Gas
  Market Impacts*](https://www.congress.gov/crs-product/R45281).
- **Directional naval-role baseline — 2019.** The Defense Intelligence Agency's
  public reference describes littoral forces, coastal-defense cruise missiles,
  small submarines, fast attack craft, and the contrast between conventional
  naval and IRGC Navy roles. It is older than the other sources and is used only
  as a role taxonomy, not a current inventory count. Source: [DIA, *Iran
  Military Power*](https://www.dia.mil/Portals/110/Images/News/Military_Powers_Publications/Iran_Military_Power_LR.pdf).

## RTS doctrine

Iran's faction identity is **distributed reconnaissance and layered denial**.
It inherits a complete Soviet-side economy and construction spine, then adds a
native-contract roster whose strength comes from combined arms rather than one
decisive super-unit.

| Capability role | RTS expression | Built-in counterplay |
| --- | --- | --- |
| Numerous reserve infantry | Basij Rifle Sections are cheap and quick to train, but individually fragile and poor against armor. | Machine guns, flame weapons, splash damage, crushing, and aircraft. |
| Dismounted anti-armor | ATGM Teams outrange tanks and hit heavy armor hard. Firing has a setup delay and the team is immobile through its long reload. | Scouts, artillery, infantry rushes, aircraft, and flanking during reload. |
| Distributed UAV control | Drone Controllers reveal a broad area, detect stealth, and provide the prerequisite for loitering munitions. | Low health, no close-range punch, and loss of the controller suspends new loitering-munition production. |
| Armored conventional force | The Karrar MBT is a durable medium-speed line tank with a conventional independently tracking turret. | Dedicated AT infantry, heavy tanks, air attack, and cost-efficient swarms. |
| Mobile air defense | The Raad vehicle combines radar vision and long-range missiles, but is weak against ground units and vulnerable while reloading. | Ground armor, artillery, stealth approach, and saturation. |
| Mobile standoff fire | The Fajr launcher attacks structures and clustered ground forces from range, then exposes an empty rack during a long reload. | Fast raiders, aircraft, counterbattery fire, and line-of-sight denial. |
| Conventional and rotary aviation | The Azar interceptor controls airspace; the Toufan gunship provides close support. Both use finite ammunition and must rearm. | Layered AA, fighters, dispersal, and attacks on their rearm bases. |
| Reusable and expendable drones | The Mohajer is a reusable scout/precision striker; the Simorgh loitering munition is cheaper and single-use. | Mobile AA, fighters, cheap screening units, and destroying Drone Controllers. |
| Littoral asymmetry | The Peykaap missile boat is fast and fragile; the Ghadir midget submarine is stealthy but slow. A coastal missile truck punishes large ships from land. | Patrol craft, detection, aircraft, depth weapons, and inland maneuver. |
| Fictional commando | Shadow One combines delayed recloaking, a suppressed anti-infantry weapon, and demolition. Moving, attacking, or sabotaging breaks stealth. | All infantry detect nearby cloak; dogs, radar-supported forces, splash damage, and area denial are stronger counters. |

## Balance guardrails

- No strategic-range, nuclear, chemical, biological, or civilian-targeting
  mechanics are included.
- Missile and loitering-munition attacks are tactical abstractions with visible
  projectiles, finite ammunition or self-consumption, and meaningful reload or
  production costs.
- Shadow One has a strict build limit of one, cannot defeat armor efficiently,
  and must expose himself to move, fire, infiltrate, or demolish.
- Native economy, movement, attack, targeting, ammunition, rearming,
  veterancy, repair, production, transport, projectile, wake, and husk systems
  remain the implementation baseline.
- Numerical balance is tuned against stock Red Alert costs and time-to-kill,
  but competitive balance remains a subjective playtest concern.
