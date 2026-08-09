import type { EarthFeature } from "../../../lib/oramap";

const overpassEndpoints = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.private.coffee/api/interpreter",
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

  const query = `[out:json][timeout:16];(
way(around:${radiusM},${latitude},${longitude})[natural~"water|coastline|bay"];
way(around:${radiusM},${latitude},${longitude})[waterway];
way(around:${radiusM},${latitude},${longitude})[highway~"motorway|trunk|primary|secondary|tertiary"];
);out tags geom;`;

  for (const endpoint of overpassEndpoints) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 18_000);
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
      if (!response.ok) continue;
      const payload = (await response.json()) as {
        elements?: Array<{
          tags?: Record<string, string>;
          geometry?: Array<{ lat: number; lon: number }>;
        }>;
      };
      const features: EarthFeature[] = (payload.elements ?? []).flatMap((element) => {
        const tags = element.tags ?? {};
        const geometry = element.geometry ?? [];
        if (geometry.length < 2) return [];
        const kind = tags.highway ? "road" : tags.waterway || tags.natural ? "water" : null;
        return kind ? [{ kind, points: geometry.map((point) => [point.lat, point.lon] as [number, number]) }] : [];
      });
      return Response.json(
        { features, provider: "OpenStreetMap / Overpass", featureCount: features.length },
        { headers: { "Cache-Control": "public, max-age=900, s-maxage=86400" } },
      );
    } catch {
      // Try the next community endpoint before returning the deterministic fallback signal.
    } finally {
      clearTimeout(timer);
    }
  }

  return Response.json({ error: "Earth data is temporarily unavailable" }, { status: 503 });
}
