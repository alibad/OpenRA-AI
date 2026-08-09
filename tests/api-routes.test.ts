import assert from "node:assert/strict";
import test from "node:test";
import { POST as earthFeatures } from "../app/api/earth-features/route";
import { GET as geocode } from "../app/api/geocode/route";

test("geocode rejects empty searches before contacting the provider", async () => {
  const response = await geocode(new Request("https://rtsai.net/api/geocode?q="));
  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { error: "Enter a place to search" });
});

test("earth feature proxy rejects invalid selections before contacting Overpass", async () => {
  const response = await earthFeatures(
    new Request("https://rtsai.net/api/earth-features", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ latitude: 91, longitude: 46.7, radiusM: 3500 }),
    }),
  );
  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { error: "Invalid Earth selection" });
});
