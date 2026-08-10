import assert from "node:assert/strict";
import test from "node:test";
import { decodeMissionBlueprint, encodeMissionBlueprint, type MissionBlueprint } from "../lib/mission-blueprint";

const blueprint: MissionBlueprint = {
  latitude: 24.7136,
  longitude: 46.6753,
  place: "Riyadh, Saudi Arabia",
  title: "Riyadh Crossing",
  radiusM: 3500,
  size: 96,
  seed: 42,
  story: "A fictional supply corridor.",
};

test("mission blueprints round-trip through a shareable query", () => {
  assert.deepEqual(decodeMissionBlueprint(encodeMissionBlueprint(blueprint)), blueprint);
});

test("mission blueprints reject unsafe coordinates and normalize unsupported settings", () => {
  assert.equal(decodeMissionBlueprint(new URLSearchParams("lat=91&lon=0")), null);
  const decoded = decodeMissionBlueprint(new URLSearchParams("lat=1&lon=2&size=999&radius=1&seed=-4"));
  assert.equal(decoded?.size, 96);
  assert.equal(decoded?.radiusM, 3500);
  assert.equal(decoded?.seed, 0);
});
