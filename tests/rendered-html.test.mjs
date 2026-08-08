import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("https://openra-ai.example/", { headers: { accept: "text/html", host: "openra-ai.example" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("renders the complete marketing and mission-creation surface", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>OpenRA AI/);
  assert.match(html, /Your battlefield/);
  assert.match(html, /Mission studio/);
  assert.match(html, /Point anywhere/);
  assert.match(html, /Download Windows alpha/);
  assert.match(html, /Play-OpenRAAI\.cmd/);
  assert.match(html, /0\.1\.0-alpha\.6/);
  assert.match(html, /AI layer/);
  assert.match(html, /OpenStreetMap contributors/);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview|react-loading-skeleton/);
});

test("ships a real browser-side OpenRA package compiler", async () => {
  const source = await readFile(new URL("../lib/oramap.ts", import.meta.url), "utf8");
  assert.match(source, /MapFormat: 12/);
  assert.match(source, /Tileset: TEMPERAT/);
  assert.match(source, /map\.bin/);
  assert.match(source, /openra-ai-manifest\.json/);
  assert.match(source, /zipSync/);
  assert.match(source, /spawn/);
});
