import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { strToU8, zipSync } from "fflate";
import { compileMissionCore, type GeoSelection } from "../lib/oramap";

const output = process.argv[2];
if (!output) throw new Error("Usage: build-openra-fixture.ts <output.oramap>");

const selection: GeoSelection = {
  latitude: 24.7136,
  longitude: 46.6753,
  title: "Browser Riyadh Crossing",
  radiusM: 3500,
  size: 64,
  seed: 42,
  story: "A browser-compiled validation skirmish.",
};
const mission = compileMissionCore(selection);
const onePixelPng = Uint8Array.from(
  Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64"),
);
const archive = zipSync(
  {
    "map.yaml": strToU8(mission.yaml),
    "map.bin": mission.binary,
    "map.png": onePixelPng,
    "openra-ai-manifest.json": strToU8(JSON.stringify({ selection, compiler: "browser" }, null, 2)),
  },
  { level: 9 },
);

await writeFile(resolve(output), archive);
