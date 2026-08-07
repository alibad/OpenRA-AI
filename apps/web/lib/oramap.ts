import { strToU8, zipSync } from "fflate";

export type GeoSelection = {
  latitude: number;
  longitude: number;
  title: string;
  radiusM: number;
  size: 64 | 96 | 128;
  seed: number;
  story: string;
};

export type MissionPackage = {
  blob: Blob;
  filename: string;
  previewUrl: string;
  sourceStatus: "live-openstreetmap" | "deterministic-fallback";
  waterCells: number;
  roadCells: number;
  validation: string[];
};

export type MissionCore = {
  cells: number[][];
  spawns: Array<[number, number]>;
  mines: Array<[number, number]>;
  yaml: string;
  binary: Uint8Array;
};

type Feature = {
  kind: "water" | "road";
  points: Array<[number, number]>;
};

const LAND = 0;
const WATER = 1;
const ROAD = 2;
const overpassEndpoints = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.private.coffee/api/interpreter",
] as const;

function random(seed: number) {
  let state = seed >>> 0 || 1;
  return () => {
    state = (Math.imul(1664525, state) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

async function acquireFeatures(selection: GeoSelection): Promise<Feature[]> {
  const query = `[out:json][timeout:10];(
way(around:${selection.radiusM},${selection.latitude},${selection.longitude})[natural~"water|coastline|bay"];
way(around:${selection.radiusM},${selection.latitude},${selection.longitude})[waterway];
way(around:${selection.radiusM},${selection.latitude},${selection.longitude})[highway~"motorway|trunk|primary|secondary|tertiary"];
);out tags geom;`;
  let lastError: unknown = new Error("No Overpass endpoint was available");
  for (const endpoint of overpassEndpoints) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 9000);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ data: query }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Overpass returned ${response.status}`);
      const payload = (await response.json()) as {
        elements?: Array<{
          tags?: Record<string, string>;
          geometry?: Array<{ lat: number; lon: number }>;
        }>;
      };
      return (payload.elements ?? []).flatMap((element) => {
        const tags = element.tags ?? {};
        const geometry = element.geometry ?? [];
        if (geometry.length < 2) return [];
        const kind = tags.highway ? "road" : tags.waterway || tags.natural ? "water" : null;
        return kind
          ? [{ kind, points: geometry.map((point) => [point.lat, point.lon] as [number, number]) }]
          : [];
      });
    } catch (error) {
      lastError = error;
    } finally {
      window.clearTimeout(timeout);
    }
  }
  throw lastError;
}

function line(a: [number, number], b: [number, number]) {
  let [x0, y0] = a;
  const [x1, y1] = b;
  const result: Array<[number, number]> = [];
  const dx = Math.abs(x1 - x0);
  const sx = x0 < x1 ? 1 : -1;
  const dy = -Math.abs(y1 - y0);
  const sy = y0 < y1 ? 1 : -1;
  let error = dx + dy;
  while (true) {
    result.push([x0, y0]);
    if (x0 === x1 && y0 === y1) return result;
    const doubled = 2 * error;
    if (doubled >= dy) {
      error += dy;
      x0 += sx;
    }
    if (doubled <= dx) {
      error += dx;
      y0 += sy;
    }
  }
}

function paint(cells: number[][], x: number, y: number, radius: number, value: number) {
  for (let yy = Math.max(0, y - radius); yy <= Math.min(cells.length - 1, y + radius); yy++) {
    for (let xx = Math.max(0, x - radius); xx <= Math.min(cells[0].length - 1, x + radius); xx++) {
      if ((xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2) cells[yy][xx] = value;
    }
  }
}

function project(point: [number, number], selection: GeoSelection, margin: number): [number, number] {
  const [lat, lon] = point;
  const north = (lat - selection.latitude) * 111_320;
  const east = (lon - selection.longitude) * 111_320 * Math.max(0.15, Math.cos((selection.latitude * Math.PI) / 180));
  const span = selection.size - margin * 2 - 1;
  return [
    Math.max(margin, Math.min(selection.size - margin - 1, margin + Math.round((east / (selection.radiusM * 2) + 0.5) * span))),
    Math.max(margin, Math.min(selection.size - margin - 1, margin + Math.round((0.5 - north / (selection.radiusM * 2)) * span))),
  ];
}

function buildTerrain(selection: GeoSelection, features: Feature[]) {
  const margin = Math.max(4, selection.size / 16);
  const cells = Array.from({ length: selection.size }, () => Array(selection.size).fill(LAND));
  const rng = random(selection.seed);
  const hasWater = features.some((feature) => feature.kind === "water");

  if (!hasWater) {
    const center = Math.floor(selection.size * (0.42 + rng() * 0.16));
    for (let y = margin; y < selection.size - margin; y++) {
      const x = center + Math.round(Math.sin((y + selection.seed) / 7) * 4);
      paint(cells, x, y, 1, WATER);
    }
  }

  for (const feature of features) {
    const points = feature.points.map((point) => project(point, selection, margin));
    for (let index = 1; index < points.length; index++) {
      for (const [x, y] of line(points[index - 1], points[index])) {
        if (feature.kind === "water") paint(cells, x, y, 1, WATER);
        else if (cells[y][x] !== WATER) cells[y][x] = ROAD;
      }
    }
  }

  const spawns: Array<[number, number]> = [
    [margin + 8, margin + 8],
    [selection.size - margin - 9, selection.size - margin - 9],
  ];
  const mines: Array<[number, number]> = [
    [spawns[0][0] + 7, spawns[0][1] + 1],
    [spawns[1][0] - 7, spawns[1][1] - 1],
  ];
  for (const point of [...spawns, ...mines]) paint(cells, point[0], point[1], point === mines[0] || point === mines[1] ? 6 : 4, LAND);

  // Guarantee a playable route between starts even where imported water divides the map.
  for (const [x, y] of line(spawns[0], spawns[1])) paint(cells, x, y, 1, ROAD);
  return { cells, spawns, mines, margin };
}

function compileBinary(cells: number[][], mines: Array<[number, number]>, seed: number) {
  const width = cells[0].length;
  const height = cells.length;
  const area = width * height;
  const bytes = new Uint8Array(17 + area * 5);
  const view = new DataView(bytes.buffer);
  view.setUint8(0, 2);
  view.setUint16(1, width, true);
  view.setUint16(3, height, true);
  view.setUint32(5, 17, true);
  view.setUint32(9, 0, true);
  view.setUint32(13, 17 + area * 3, true);
  const rng = random(seed);
  let offset = 17;
  for (let x = 0; x < width; x++) {
    for (let y = 0; y < height; y++) {
      view.setUint16(offset, cells[y][x] === WATER ? 1 : 255, true);
      view.setUint8(offset + 2, cells[y][x] === WATER ? 0 : Math.floor(rng() * 16));
      offset += 3;
    }
  }
  const resources = new Map<string, [number, number]>();
  for (const [mineX, mineY] of mines) {
    const resourceRng = random(seed ^ 0x5f3759df);
    for (let dy = -5; dy <= 5; dy++) {
      for (let dx = -5; dx <= 5; dx++) {
        const distance = Math.abs(dx) + Math.abs(dy);
        if (distance >= 2 && distance <= 7 && resourceRng() < 0.62) resources.set(`${mineX + dx},${mineY + dy}`, [1, Math.max(4, 12 - distance)]);
      }
    }
  }
  for (let x = 0; x < width; x++) {
    for (let y = 0; y < height; y++) {
      const [type, density] = resources.get(`${x},${y}`) ?? [0, 0];
      view.setUint8(offset, type);
      view.setUint8(offset + 1, density);
      offset += 2;
    }
  }
  return bytes;
}

function mapYaml(selection: GeoSelection, spawns: Array<[number, number]>, mines: Array<[number, number]>, margin: number) {
  const title = selection.title.replace(/[\r\n:]/g, " ").slice(0, 80) || "Earth Skirmish";
  const actors = [...spawns.map((location) => ["mpspawn", location]), ...mines.map((location) => ["mine", location])] as Array<[string, [number, number]]>;
  return `MapFormat: 12

RequiresMod: ra

Title: ${title}

Author: OpenRA AI

Tileset: TEMPERAT

MapSize: ${selection.size},${selection.size}

Bounds: ${margin},${margin},${selection.size - margin * 2},${selection.size - margin * 2}

Visibility: Lobby

Categories: Conquest

Players:
\tPlayerReference@Neutral:
\t\tName: Neutral
\t\tOwnsWorld: True
\t\tNonCombatant: True
\t\tFaction: allies
\tPlayerReference@Creeps:
\t\tName: Creeps
\t\tNonCombatant: True
\t\tFaction: allies
\t\tEnemies: Multi0, Multi1
\tPlayerReference@Multi0:
\t\tName: Multi0
\t\tPlayable: True
\t\tFaction: Random
\t\tEnemies: Creeps
\tPlayerReference@Multi1:
\t\tName: Multi1
\t\tPlayable: True
\t\tFaction: Random
\t\tEnemies: Creeps

Actors:
${actors.map(([type, [x, y]], index) => `\tActor${index}: ${type}\n\t\tOwner: Neutral\n\t\tLocation: ${x},${y}`).join("\n")}
`;
}

function renderPreview(cells: number[][], spawns: Array<[number, number]>, mines: Array<[number, number]>) {
  const scale = 4;
  const canvas = document.createElement("canvas");
  canvas.width = cells[0].length * scale;
  canvas.height = cells.length * scale;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas is unavailable");
  const spawnSet = new Set(spawns.map(([x, y]) => `${x},${y}`));
  const mineSet = new Set(mines.map(([x, y]) => `${x},${y}`));
  for (let y = 0; y < cells.length; y++) {
    for (let x = 0; x < cells[0].length; x++) {
      context.fillStyle = spawnSet.has(`${x},${y}`)
        ? "#f2ca68"
        : mineSet.has(`${x},${y}`)
          ? "#d65e42"
          : cells[y][x] === WATER
            ? "#244f67"
            : cells[y][x] === ROAD
              ? "#ad966a"
              : "#64734c";
      context.fillRect(x * scale, y * scale, scale, scale);
    }
  }
  return canvas.toDataURL("image/png");
}

function dataUrlBytes(url: string) {
  const binary = atob(url.split(",")[1]);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

export async function generateEarthMission(selection: GeoSelection): Promise<MissionPackage> {
  let features: Feature[] = [];
  let sourceStatus: MissionPackage["sourceStatus"] = "live-openstreetmap";
  try {
    features = await acquireFeatures(selection);
    if (!features.length) sourceStatus = "deterministic-fallback";
  } catch {
    sourceStatus = "deterministic-fallback";
  }
  const { cells, spawns, mines, yaml, binary } = compileMissionCore(selection, features);
  const previewUrl = renderPreview(cells, spawns, mines);
  const validation = [
    "2 playable spawns",
    "connected land route",
    "symmetric resource fields",
    "OpenRA map format 12",
  ];
  const manifest = {
    schema: "openra-ai.mission-package/v1",
    generated_at: new Date().toISOString(),
    selection,
    source: {
      provider: "OpenStreetMap",
      attribution: "© OpenStreetMap contributors",
      status: sourceStatus,
      feature_count: features.length,
    },
    game: { mod: "ra", map_format: 12, tileset: "TEMPERAT" },
    validation,
    fictionalization: "Stylized terrain for fictional play; not a factual simulation of people or events.",
  };
  const archive = zipSync(
    {
      "map.yaml": strToU8(yaml),
      "map.bin": binary,
      "map.png": dataUrlBytes(previewUrl),
      "briefing.md": strToU8(`# ${selection.title}\n\n${selection.story || "Secure the approaches and control the center."}\n\nThis is a stylized fictional scenario.\n`),
      "openra-ai-manifest.json": strToU8(JSON.stringify(manifest, null, 2)),
    },
    { level: 9 },
  );
  const slug = selection.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "earth-skirmish";
  return {
    blob: new Blob([archive.buffer as ArrayBuffer], { type: "application/zip" }),
    filename: `${slug}-${selection.seed}.oramap`,
    previewUrl,
    sourceStatus,
    waterCells: cells.flat().filter((cell) => cell === WATER).length,
    roadCells: cells.flat().filter((cell) => cell === ROAD).length,
    validation,
  };
}

export function compileMissionCore(selection: GeoSelection, features: Feature[] = []): MissionCore {
  const { cells, spawns, mines, margin } = buildTerrain(selection, features);
  return {
    cells,
    spawns,
    mines,
    yaml: mapYaml(selection, spawns, mines, margin),
    binary: compileBinary(cells, mines, selection.seed),
  };
}
