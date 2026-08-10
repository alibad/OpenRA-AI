import type { GeoSelection } from "./oramap";

export type MissionBlueprint = GeoSelection & { place: string };

const allowedSizes = new Set([64, 96, 128]);
const allowedRadii = new Set([2000, 3500, 6000]);

export function encodeMissionBlueprint(blueprint: MissionBlueprint) {
  return new URLSearchParams({
    lat: blueprint.latitude.toFixed(5),
    lon: blueprint.longitude.toFixed(5),
    title: blueprint.title.slice(0, 80),
    place: blueprint.place.slice(0, 160),
    radius: String(blueprint.radiusM),
    size: String(blueprint.size),
    seed: String(Math.max(0, Math.floor(blueprint.seed))),
    story: blueprint.story.slice(0, 240),
  });
}

export function decodeMissionBlueprint(params: URLSearchParams): MissionBlueprint | null {
  if (!params.has("lat") || !params.has("lon")) return null;
  const latitude = Number(params.get("lat"));
  const longitude = Number(params.get("lon"));
  const rawSize = Number(params.get("size"));
  const rawRadius = Number(params.get("radius"));
  const rawSeed = Number(params.get("seed"));
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90 || !Number.isFinite(longitude) || longitude < -180 || longitude > 180)
    return null;

  return {
    latitude,
    longitude,
    title: (params.get("title") || "Shared Earth Skirmish").slice(0, 80),
    place: (params.get("place") || `Pinned at ${latitude.toFixed(4)}, ${longitude.toFixed(4)}`).slice(0, 160),
    radiusM: allowedRadii.has(rawRadius) ? rawRadius : 3500,
    size: (allowedSizes.has(rawSize) ? rawSize : 96) as 64 | 96 | 128,
    seed: Number.isFinite(rawSeed) ? Math.max(0, Math.min(2_147_483_647, Math.floor(rawSeed))) : 42,
    story: (params.get("story") || "Secure the approaches and control the center.").slice(0, 240),
  };
}
