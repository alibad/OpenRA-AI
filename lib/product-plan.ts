export type ProductLayer = {
  id: "companion" | "world" | "distribution";
  number: string;
  status: string;
  title: string;
  description: string;
  outcome: string;
};

export const productLayers: ProductLayer[] = [
  {
    id: "companion",
    number: "01",
    status: "Playable",
    title: "Companion + command",
    description: "An interruptible partner that notices, explains, speaks, proposes safe actions, and can take optional AUTO command.",
    outcome: "Human-led play with useful intelligence inside the match.",
  },
  {
    id: "world",
    number: "02",
    status: "Playable alpha",
    title: "Earth to battlefield",
    description: "Choose a real place, interpret its terrain, and let OpenRA build and validate an editable battlefield from that evidence.",
    outcome: "A world-scale source of playable missions and skirmishes.",
  },
  {
    id: "distribution",
    number: "03",
    status: "Live web app",
    title: "Discover + launch",
    description: "The web studio lets people discover the project, build and share mission blueprints, download verified releases, and move into the native game.",
    outcome: "One approachable doorway into the companion and creation tools.",
  },
];

export const developmentTracks = [
  {
    id: "creation" as const,
    label: "Expansion track",
    title: "New theatres + mods",
    description: "Reusable factions, units, art, voices, objectives, campaigns, and complete authored experiences.",
  },
  {
    id: "autonomy" as const,
    label: "R&D track",
    title: "Agents that play + learn",
    description: "Bounded headless matches with recorded evidence, graded outcomes, and lessons for stronger native strategy.",
  },
];

export const currentShowcase = {
  slug: "red-sea-2026",
  label: "Current playable proof",
  title: "Red Sea 2026",
  mission: "Jizan Corridor",
  description:
    "A focused vertical slice proving the platform can move beyond a generated skirmish: two countries, faction-gated units, native bot priorities, and a source-dated Earth mission contract.",
  highlights: ["Saudi Arabia + Yemen", "Signature unit rosters", "Earth-derived mission contract"],
  image: "/red-sea-2026-key-art.webp",
  docsPath: "/blob/main/docs/red-sea-2026.md",
  launcher: "Play-Red-Sea-2026.cmd",
};
