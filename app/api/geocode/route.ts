type NominatimResult = {
  lat: string;
  lon: string;
  display_name: string;
  type?: string;
};

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams.get("q")?.trim();
  if (!query) return Response.json({ error: "Enter a place to search" }, { status: 400 });

  const upstream = new URL("https://nominatim.openstreetmap.org/search");
  upstream.searchParams.set("format", "jsonv2");
  upstream.searchParams.set("limit", "5");
  upstream.searchParams.set("addressdetails", "1");
  upstream.searchParams.set("q", query.slice(0, 160));

  try {
    const response = await fetch(upstream, {
      headers: {
        Accept: "application/json",
        "Accept-Language": "en",
        "User-Agent": "RTS-AI/1.0 (https://rtsai.net)",
      },
    });
    if (!response.ok) throw new Error(`Geocoder returned ${response.status}`);
    const results = (await response.json()) as NominatimResult[];
    return Response.json(
      {
        results: results.map((result) => ({
          latitude: Number(result.lat),
          longitude: Number(result.lon),
          label: result.display_name,
          kind: result.type ?? "place",
        })),
        attribution: "OpenStreetMap contributors",
      },
      { headers: { "Cache-Control": "public, max-age=900, s-maxage=86400" } },
    );
  } catch {
    return Response.json({ error: "Place search is temporarily unavailable" }, { status: 503 });
  }
}
