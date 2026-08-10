import type { EarthFeature } from "../../../lib/oramap";
import { verifyFirebaseRequest } from "../../../lib/firebase-token";

const overpassEndpoints = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.private.coffee/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
] as const;

type EarthRequest = { latitude?: number; longitude?: number; radiusM?: number };

export async function POST(request: Request) {
  let input: EarthRequest;
  try {
    input = (await request.json()) as EarthRequest;
  } catch {
    return Response.json({ error: "Invalid request" }, { status: 400 });
  }

  const latitude = Number(input.latitude);
  const longitude = Number(input.longitude);
  const radiusM = Math.round(Number(input.radiusM));
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90 || !Number.isFinite(longitude) || longitude < -180 || longitude > 180 || !Number.isFinite(radiusM) || radiusM < 500 || radiusM > 12000)
    return Response.json({ error: "Invalid Earth selection" }, { status: 400 });

  const userId = await verifyFirebaseRequest(request);
  if (!userId) return Response.json({ error: "Sign in required" }, { status: 401 });

  const query = `[out:json][timeout:10];(
way(around:${radiusM},${latitude},${longitude})[natural~"water|coastline|bay"];
way(around:${radiusM},${latitude},${longitude})[waterway];
way(around:${radiusM},${latitude},${longitude})[highway~"motorway|trunk|primary|secondary|tertiary"];
);out tags geom;`;

  async function queryEndpoint(endpoint: string) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12_000);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "User-Agent": "RTS-AI/1.0 (https://rtsai.net)",
        },
        body: new URLSearchParams({ data: query }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Overpass returned ${response.status}`);
      return (await response.json()) as {
        elements?: Array<{
          tags?: Record<string, string>;
          geometry?: Array<{ lat: number; lon: number }>;
        }>;
      };
    } finally {
      clearTimeout(timer);
    }
  }

  try {
    // Race independent community mirrors so an overloaded provider does not
    // stall the entire in-game generation experience.
    const payload = await Promise.any(overpassEndpoints.map(queryEndpoint));
    const features: EarthFeature[] = (payload.elements ?? []).flatMap((element) => {
      const tags = element.tags ?? {};
      const geometry = element.geometry ?? [];
      if (geometry.length < 2) return [];
      const kind = tags.highway ? "road" : tags.waterway || tags.natural ? "water" : null;
      return kind ? [{ kind, points: geometry.map((point) => [point.lat, point.lon] as [number, number]) }] : [];
    });
    return Response.json(
      { features, provider: "OpenStreetMap / Overpass", featureCount: features.length },
      { headers: { "Cache-Control": "private, max-age=900" } },
    );
  } catch {
    return Response.json({ error: "Earth data is temporarily unavailable" }, { status: 503 });
  }
}
