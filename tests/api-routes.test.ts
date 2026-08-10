import assert from "node:assert/strict";
import test from "node:test";
import { POST as earthFeatures } from "../app/api/earth-features/route";
import { GET as geocode } from "../app/api/geocode/route";
import { POST as feedback } from "../app/api/feedback/route";

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

test("earth feature proxy requires a signed-in Firebase user", async () => {
  const response = await earthFeatures(
    new Request("https://rtsai.net/api/earth-features", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ latitude: 24.7, longitude: 46.7, radiusM: 3500 }),
    }),
  );
  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: "Sign in required" });
});

test("feedback requires a signed-in Firebase user", async () => {
  const response = await feedback(
    new Request("https://rtsai.net/api/feedback", {
      method: "POST",
      headers: { "content-type": "application/json", origin: "https://rtsai.net" },
      body: JSON.stringify({
        category: "idea",
        rating: 5,
        message: "A useful piece of feedback.",
        clientSubmissionId: "7a82cb1e-7d34-4e5a-9b9d-8106391e1cd0",
      }),
    }),
  );
  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: "Sign in required" });
});
