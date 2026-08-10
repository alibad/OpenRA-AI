import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("https://rtsai.net/", { headers: { accept: "text/html", host: "rtsai.net" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("renders the complete marketing and mission-creation surface", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>RTS AI/);
  assert.match(html, /rel="canonical" href="https:\/\/rtsai\.net\/?"/);
  assert.match(html, /name="robots" content="index, follow/);
  assert.match(html, /property="og:image" content="https:\/\/rtsai\.net\/social-card\.png"/);
  assert.match(html, /href="\/manifest\.webmanifest"/);
  assert.match(html, /\/brand\/rtsai-mark-64\.png/);
  assert.match(html, /application\/ld\+json/);
  assert.match(html, /"SoftwareApplication"/);
  assert.match(html, /"VideoGame"/);
  assert.match(html, /Your battlefield/);
  assert.match(html, /Mission studio/);
  assert.match(html, /Point anywhere/);
  assert.match(html, /Earth footprint/);
  assert.match(html, /Variation seed/);
  assert.match(html, /Same seed reproduces the same terrain/);
  assert.match(html, /Reroll/);
  assert.match(html, /Read geometry/);
  assert.match(html, /Build terrain/);
  assert.match(html, /Interactive AI companion preview/);
  assert.match(html, /Portable, checksum published/);
  assert.match(html, /Download Windows alpha/);
  assert.match(html, /Play-OpenRAAI\.cmd/);
  assert.match(html, /0\.1\.0-alpha\.8/);
  assert.match(html, /AI layer/);
  assert.match(html, /OpenStreetMap contributors/);
  assert.match(html, /EA has not endorsed and does not support this product/);
  assert.match(html, /data-analytics-event="game-download"/);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview|react-loading-skeleton/);
});

test("ships crawl, install, and brand assets", async () => {
  const robots = await readFile(new URL("../app/robots.ts", import.meta.url), "utf8");
  const sitemap = await readFile(new URL("../app/sitemap.ts", import.meta.url), "utf8");
  const manifest = await readFile(new URL("../app/manifest.ts", import.meta.url), "utf8");
  const favicon = await readFile(new URL("../public/favicon.ico", import.meta.url));
  const socialCard = await readFile(new URL("../public/social-card.png", import.meta.url));

  assert.match(robots, /sitemap: "https:\/\/rtsai\.net\/sitemap\.xml"/);
  assert.match(sitemap, /url: "https:\/\/rtsai\.net\/"/);
  assert.match(manifest, /short_name: "RTS AI"/);
  assert.match(manifest, /purpose: "maskable"/);
  assert.ok(favicon.byteLength > 1000);
  assert.ok(socialCard.byteLength > 10_000);
});

test("ships a real browser-side OpenRA package compiler", async () => {
  const source = await readFile(new URL("../lib/oramap.ts", import.meta.url), "utf8");
  assert.match(source, /MapFormat: 12/);
  assert.match(source, /Tileset: TEMPERAT/);
  assert.match(source, /map\.bin/);
  assert.match(source, /openra-ai-manifest\.json/);
  assert.match(source, /zipSync/);
  assert.match(source, /spawn/);
  assert.match(source, /\/api\/earth-features/);
});
