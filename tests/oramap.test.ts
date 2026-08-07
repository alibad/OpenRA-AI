import assert from "node:assert/strict";
import test from "node:test";
import { compileMissionCore, type GeoSelection } from "../lib/oramap";

const selection: GeoSelection = {
  latitude: 24.7136,
  longitude: 46.6753,
  title: "Riyadh Crossing",
  radiusM: 3500,
  size: 64,
  seed: 42,
  story: "A fictional supply corridor.",
};

test("browser compiler emits an OpenRA format-12 binary", () => {
  const mission = compileMissionCore(selection);
  const view = new DataView(mission.binary.buffer);
  assert.equal(view.getUint8(0), 2);
  assert.equal(view.getUint16(1, true), 64);
  assert.equal(view.getUint16(3, true), 64);
  assert.equal(view.getUint32(5, true), 17);
  assert.equal(view.getUint32(9, true), 0);
  assert.equal(view.getUint32(13, true), 17 + 64 * 64 * 3);
  assert.equal(mission.binary.byteLength, 17 + 64 * 64 * 5);
  assert.match(mission.yaml, /MapFormat: 12/);
  assert.match(mission.yaml, /Tileset: TEMPERAT/);
  assert.equal(mission.spawns.length, 2);
  assert.equal(mission.mines.length, 2);
});

test("browser map compilation is deterministic", () => {
  const first = compileMissionCore(selection);
  const second = compileMissionCore(selection);
  assert.deepEqual(first.binary, second.binary);
  assert.equal(first.yaml, second.yaml);
});
