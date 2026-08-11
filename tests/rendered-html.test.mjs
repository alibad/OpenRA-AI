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
  assert.match(html, /Locally built and smoke-tested/);
  assert.match(html, /Download Windows setup/);
  assert.match(html, /Portable ZIP/);
  assert.match(html, /Signed macOS download pending|Apple silicon/);
  assert.match(html, /Install or extract/);
  assert.match(html, /0\.1\.0-alpha\.9/);
  assert.match(html, /Red Sea 2026/);
  assert.match(html, /Jizan Corridor/);
  assert.match(html, /Play-Red-Sea-2026\.cmd/);
  assert.match(html, /Optional Local AI Pack/);
  assert.match(html, /Qwen3-VL/);
  assert.match(html, /red-sea-2026-key-art\.webp/);
  assert.match(html, /AUTO is optional/);
  assert.match(html, /AI layer/);
  assert.doesNotMatch(html, /Help improve RTS AI/);
  assert.match(html, /href="\/privacy"/);
  assert.match(html, /OpenStreetMap contributors/);
  assert.match(html, /EA has not endorsed and does not support this product/);
  assert.match(html, /data-analytics-event="game-download"/);
  assert.match(html, />Feedback</);
  assert.match(html, /windows-x64-setup\.exe/);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview|react-loading-skeleton/);
});

test("keeps account identity out of Analytics event parameters", async () => {
  const analytics = await readFile(new URL("../lib/firebase-client.ts", import.meta.url), "utf8");
  const auth = await readFile(new URL("../app/components/AuthProvider.tsx", import.meta.url), "utf8");
  const authDialog = await readFile(new URL("../app/components/AuthDialog.tsx", import.meta.url), "utf8");
  const accountNav = await readFile(new URL("../app/components/AccountNav.tsx", import.meta.url), "utf8");
  const missionStudio = await readFile(new URL("../app/components/MissionStudio.tsx", import.meta.url), "utf8");
  const privacy = await readFile(new URL("../app/privacy/page.tsx", import.meta.url), "utf8");
  const feedback = await readFile(new URL("../app/components/FeedbackPanel.tsx", import.meta.url), "utf8");

  assert.match(analytics, /setUserId\(analytics, uid\)/);
  assert.doesNotMatch(analytics, /setUserId\(analytics,.*displayName/);
  assert.doesNotMatch(analytics, /setUserId\(analytics,.*email/);
  assert.doesNotMatch(auth, /rtsai-analytics-consent/);
  assert.match(authDialog, /GoogleAuthProvider/);
  assert.match(authDialog, /signInWithPopup/);
  assert.match(authDialog, /Sign up with Google/);
  assert.match(accountNav, /Sign in/);
  assert.match(accountNav, /user\.photoURL/);
  assert.match(accountNav, /providerData\.find/);
  assert.match(accountNav, /referrerPolicy="no-referrer"/);
  assert.match(accountNav, /accountInitials/);
  assert.match(missionStudio, /Account required for AI work/);
  assert.match(privacy, /do not send your name, email/);
  assert.match(privacy, /Written feedback and diagnostics are never sent to Google Analytics/);
  assert.doesNotMatch(feedback, /trackAnalyticsEvent|feedback_submitted/);
  assert.match(feedback, /Select page element/);
  assert.match(feedback, /getConsoleLogs/);
  assert.match(feedback, /getNetworkLogs/);
});

test("ships crawl, install, and brand assets", async () => {
  const robots = await readFile(new URL("../app/robots.ts", import.meta.url), "utf8");
  const sitemap = await readFile(new URL("../app/sitemap.ts", import.meta.url), "utf8");
  const manifest = await readFile(new URL("../app/manifest.ts", import.meta.url), "utf8");
  const favicon = await readFile(new URL("../public/favicon.ico", import.meta.url));
  const socialCard = await readFile(new URL("../public/social-card.png", import.meta.url));
  const googleLogo = await readFile(new URL("../public/brand/google-g.png", import.meta.url));
  const redSeaKeyArt = await readFile(new URL("../public/red-sea-2026-key-art.webp", import.meta.url));

  assert.match(robots, /sitemap: "https:\/\/rtsai\.net\/sitemap\.xml"/);
  assert.match(sitemap, /url: "https:\/\/rtsai\.net\/"/);
  assert.match(manifest, /short_name: "RTS AI"/);
  assert.match(manifest, /purpose: "maskable"/);
  assert.ok(favicon.byteLength > 1000);
  assert.ok(socialCard.byteLength > 10_000);
  assert.ok(googleLogo.byteLength > 500);
  assert.ok(redSeaKeyArt.byteLength > 100_000);
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

test("discovers native Windows and macOS release assets", async () => {
  const source = await readFile(new URL("../lib/release.ts", import.meta.url), "utf8");
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(source, /windows-x64-setup\\\.exe/);
  assert.match(source, /macos-\(arm64\|x64\)\\\.dmg/);
  assert.match(source, /installerChecksumUrl/);
  assert.match(source, /AI-Pack-/);
  assert.match(source, /aiPackChecksumUrl/);
  assert.match(page, /No placeholder download/);
});
