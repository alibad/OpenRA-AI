briefing =
    FICTIONAL EXERCISE — 12 AUGUST 2026

    The Obsidian Directorate has disrupted the Haitan Test Range command picture and occupied the eastern control node. Restore the tactical network, open a northern sea lane, and land Sea Dragon amphibious vehicles on the eastern shore. Then coordinate armor, aviation, missiles, drones, and naval fire to disable the spectrum jammers and capture the exercise objective by destroying the control node.

    Move the Battlefield Network Specialist to the relay and deploy it. Sea Dragons only count toward the landing after passing the marked sea gate. Portable Missile Teams can deploy to switch from anti-armor to anti-air mode.

    This scenario, opponent, force disposition, locations, timing, and outcome are fictional gameplay abstractions. It does not recreate a real attack.

deploy-network-specialist = Move and deploy the Battlefield Network Specialist beside the relay.
complete-amphibious-landing = Route Sea Dragon IFVs through the sea gate and land them on the eastern beach.
destroy-control-node = Disable the three spectrum jammers and destroy the eastern control node.
protect-network-relay = Keep the western network relay operational.

actor-haitan-network-relay =
    .name = Network Relay
actor-haitan-command-node =
    .name = Obsidian Control Node
actor-haitan-spectrum-jammer =
    .name = Spectrum Jammer

exercise-control = Exercise Control / Yanxun Kongzhi
radio-haitan-opening-zh = The exercise range is being jammed. Deploy the network specialist and restore the battlefield information link.
radio-haitan-network-en = Network picture restored. Amphibious route data is now available.
radio-haitan-amphibious-zh = The amphibious group has entered the bay. Cover the landing force.
radio-haitan-combined-en = Coordinate armor, aviation, and naval fire on the final control node.
radio-haitan-warning-zh = Drone tracks detected. Switch Portable Missile Teams to anti-air mode.
radio-haitan-secure-en = Exercise control confirms all network nodes secure.

mission-text-haitan-network = Move the Network Specialist to the relay, then use Deploy to bring its sensor/jammer suite online.
mission-text-haitan-landing = Amphibious IFVs landed: { $landed } / { $required }
