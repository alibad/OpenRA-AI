"use client";

import {
  Check,
  Crosshair,
  Download,
  LoaderCircle,
  LocateFixed,
  MapPin,
  RefreshCw,
  Search,
  Share2,
  Shuffle,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Map as MapLibreMap, Marker } from "maplibre-gl";
import { generateEarthMission, type MissionPackage } from "../../lib/oramap";
import { decodeMissionBlueprint, encodeMissionBlueprint } from "../../lib/mission-blueprint";
import type { WindowsRelease } from "../../lib/release";
import { useAuth } from "./AuthProvider";
import { trackAnalyticsEvent } from "../../lib/firebase-client";

type LocationResult = { latitude: number; longitude: number; label: string; kind?: string };

const presets = [
  { label: "Riyadh", latitude: 24.7136, longitude: 46.6753 },
  { label: "Manhattan", latitude: 40.7128, longitude: -74.006 },
  { label: "Tokyo Bay", latitude: 35.6329, longitude: 139.797 },
  { label: "Cape Town", latitude: -33.9249, longitude: 18.4241 },
];

function randomInteger(max: number) {
  const value = new Uint32Array(1);
  window.crypto.getRandomValues(value);
  return value[0] % max;
}

export function MissionStudio({ windowsRelease }: { windowsRelease: WindowsRelease }) {
  const { user, loading: authLoading, openAuth } = useAuth();
  const mapNode = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const generationControllerRef = useRef<AbortController | null>(null);
  const [latitude, setLatitude] = useState(24.7136);
  const [longitude, setLongitude] = useState(46.6753);
  const [title, setTitle] = useState("Riyadh Crossing");
  const [seed, setSeed] = useState(42);
  const [story, setStory] = useState("A contested supply corridor cuts across the city edge.");
  const [size, setSize] = useState<64 | 96 | 128>(96);
  const [radiusM, setRadiusM] = useState(3500);
  const [selectedPlace, setSelectedPlace] = useState("Riyadh, Saudi Arabia");
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<LocationResult[]>([]);
  const [status, setStatus] = useState<"idle" | "locating" | "acquiring" | "compiling" | "ready" | "error">("idle");
  const [mission, setMission] = useState<(MissionPackage & { downloadUrl: string }) | null>(null);
  const [error, setError] = useState("");
  const [generationMs, setGenerationMs] = useState(0);
  const [shareStatus, setShareStatus] = useState<"idle" | "copied" | "error">("idle");

  useEffect(() => {
    let cancelled = false;
    let map: MapLibreMap | null = null;
    void import("maplibre-gl").then((maplibre) => {
      if (cancelled || !mapNode.current) return;
      const shared = decodeMissionBlueprint(new URLSearchParams(window.location.search));
      const initialLatitude = shared?.latitude ?? latitude;
      const initialLongitude = shared?.longitude ?? longitude;
      if (shared) {
        setLatitude(shared.latitude);
        setLongitude(shared.longitude);
        setTitle(shared.title);
        setSelectedPlace(shared.place);
        setRadiusM(shared.radiusM);
        setSize(shared.size);
        setSeed(shared.seed);
        setStory(shared.story);
      }
      map = new maplibre.Map({
        container: mapNode.current,
        center: [initialLongitude, initialLatitude],
        zoom: 10.4,
        attributionControl: false,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              attribution: "© OpenStreetMap contributors",
            },
          },
          layers: [{ id: "osm", type: "raster", source: "osm", paint: { "raster-saturation": -0.78, "raster-contrast": 0.14, "raster-brightness-max": 0.72 } }],
        },
      });
      map.addControl(new maplibre.NavigationControl({ showCompass: false }), "bottom-right");
      markerRef.current = new maplibre.Marker({ color: "#ef5b3f" }).setLngLat([initialLongitude, initialLatitude]).addTo(map);
      map.on("click", (event) => {
        const lat = Number(event.lngLat.lat.toFixed(5));
        const lon = Number(event.lngLat.lng.toFixed(5));
        setLatitude(lat);
        setLongitude(lon);
        setSelectedPlace(`Pinned at ${lat.toFixed(4)}, ${lon.toFixed(4)}`);
        markerRef.current?.setLngLat([lon, lat]);
        setMission(null);
        setStatus("idle");
        setError("");
        setSearchResults([]);
      });
      mapRef.current = map;
    });
    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
    };
    // The map owns subsequent coordinate updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => generationControllerRef.current?.abort(), []);

  useEffect(() => {
    const downloadUrl = mission?.downloadUrl;
    return () => {
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    };
  }, [mission?.downloadUrl]);

  function moveTo(next: { label: string; latitude: number; longitude: number }, fullLabel = next.label) {
    setLatitude(next.latitude);
    setLongitude(next.longitude);
    setTitle(`${next.label} Crossing`);
    setSelectedPlace(fullLabel);
    markerRef.current?.setLngLat([next.longitude, next.latitude]);
    mapRef.current?.flyTo({ center: [next.longitude, next.latitude], zoom: 10.5 });
    setMission(null);
    setStatus("idle");
    setError("");
    setSearchResults([]);
    setShareStatus("idle");
  }

  async function locate() {
    if (!search.trim()) return;
    setStatus("locating");
    setError("");
    try {
      const response = await fetch(`/api/geocode?q=${encodeURIComponent(search)}`);
      if (!response.ok) throw new Error("Place search is unavailable");
      const payload = (await response.json()) as { results?: LocationResult[] };
      const results = payload.results ?? [];
      void trackAnalyticsEvent("place_search", { result_count: results.length });
      if (!results.length) throw new Error("No place matched that search");
      setSearchResults(results);
      setStatus("idle");
      if (results.length === 1) chooseLocation(results[0]);
    } catch (cause) {
      setStatus("error");
      setError(cause instanceof Error ? cause.message : "Could not locate that place");
    }
  }

  function chooseLocation(result: LocationResult) {
    moveTo({ label: result.label.split(",")[0], latitude: result.latitude, longitude: result.longitude }, result.label);
    setSearch("");
  }

  async function generate(nextSeed = seed) {
    if (!user) {
      void trackAnalyticsEvent("auth_gate_view", { feature: "mission_generation" });
      openAuth("Create an account to generate and validate this battlefield");
      return;
    }
    generationControllerRef.current?.abort();
    const controller = new AbortController();
    generationControllerRef.current = controller;
    const startedAt = performance.now();
    setStatus("acquiring");
    setError("");
    setMission(null);
    setGenerationMs(0);
    void trackAnalyticsEvent("mission_generation_started", { map_size: size, footprint_km: Math.round(radiusM * 2 / 1000) });
    try {
      const authToken = await user.getIdToken();
      const result = await generateEarthMission({
        latitude,
        longitude,
        title,
        radiusM,
        size,
        seed: nextSeed,
        story,
      }, {
        signal: controller.signal,
        authToken,
        onStage: setStatus,
      });
      const downloadUrl = URL.createObjectURL(result.blob);
      setMission({ ...result, downloadUrl });
      setGenerationMs(Math.round(performance.now() - startedAt));
      setStatus("ready");
      void trackAnalyticsEvent("mission_generation_completed", {
        map_size: size,
        footprint_km: Math.round(radiusM * 2 / 1000),
        source: result.sourceStatus,
        duration_band: performance.now() - startedAt < 5000 ? "under_5s" : "5s_or_more",
      });
    } catch (cause) {
      if (controller.signal.aborted) {
        setStatus("idle");
        setError("Generation cancelled. Your mission setup is preserved.");
        return;
      }
      setStatus("error");
      setError(cause instanceof Error && cause.message === "Authentication required" ? "Your session expired. Sign in again to generate this mission." : cause instanceof Error ? cause.message : "Mission compilation failed");
      void trackAnalyticsEvent("mission_generation_failed", { stage: status });
    } finally {
      if (generationControllerRef.current === controller) generationControllerRef.current = null;
    }
  }

  function cancelGeneration() {
    generationControllerRef.current?.abort();
  }

  async function copyBlueprint() {
    try {
      const url = new URL(window.location.href);
      url.search = encodeMissionBlueprint({ latitude, longitude, title, place: selectedPlace, radiusM, size, seed, story }).toString();
      url.hash = "mission-studio";
      await navigator.clipboard.writeText(url.toString());
      setShareStatus("copied");
      void trackAnalyticsEvent("mission_blueprint_shared");
      window.setTimeout(() => setShareStatus("idle"), 2200);
    } catch {
      setShareStatus("error");
    }
  }

  function generateVariation() {
    const nextSeed = (seed + 7919) % 2_147_483_647;
    setSeed(nextSeed);
    void trackAnalyticsEvent("mission_variation_requested", { map_size: size });
    void generate(nextSeed);
  }

  function clearGeneratedMission() {
    generationControllerRef.current?.abort();
    setMission(null);
    setStatus("idle");
    setError("");
    setGenerationMs(0);
    setShareStatus("idle");
  }

  function rerollSeed() {
    setSeed(randomInteger(2_147_483_647));
    clearGeneratedMission();
  }

  function surpriseMe() {
    const next = presets[randomInteger(presets.length)];
    moveTo(next);
    setSeed(randomInteger(999_999));
    setStory(`A fictional flashpoint forms around the approaches to ${next.label}. Secure the routes and control the resources.`);
  }

  const pipelineStep = status === "ready" ? 4 : status === "compiling" ? 3 : status === "acquiring" ? 2 : status === "locating" ? 1 : 0;

  return (
    <section className="studio-shell" id="mission-studio" aria-labelledby="studio-title">
      <div className="studio-heading">
        <div>
          <span className="eyebrow"><Crosshair size={14} /> Mission studio / alpha</span>
          <h2 id="studio-title">Point anywhere. Leave with a battlefield.</h2>
        </div>
        <p>Search or click anywhere, tune the battlefield footprint, then compile a validated Red Alert map in your browser.</p>
      </div>

      <div className="studio-grid">
        <div className="map-panel">
          <div className="map-toolbar">
            <div className="search-field">
              <Search size={16} aria-hidden="true" />
              <input
                value={search}
                onChange={(event) => { setSearch(event.target.value); setSearchResults([]); }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void locate();
                  if (event.key === "Escape") setSearchResults([]);
                }}
                placeholder="Find a city, coast, or landmark"
                aria-label="Find a location"
                aria-controls="location-results"
              />
              <button onClick={() => void locate()} aria-label="Search location" disabled={status === "locating"}>
                {status === "locating" ? <LoaderCircle className="spin" size={14} /> : "Go"}
              </button>
            </div>
            {searchResults.length > 0 && (
              <div className="location-results" id="location-results" role="region" aria-live="polite" aria-label={`${searchResults.length} location results`}>
                <div><span>Choose the exact place</span><button onClick={() => setSearchResults([])} aria-label="Close location results"><X size={14} /></button></div>
                <ul>
                  {searchResults.map((result) => {
                    const [name, ...detail] = result.label.split(",");
                    return <li key={`${result.latitude}-${result.longitude}`}><button onClick={() => chooseLocation(result)}><strong>{name}</strong><span>{detail.join(",").trim()}</span><small>{result.kind ?? "place"}</small></button></li>;
                  })}
                </ul>
              </div>
            )}
            <span className="coordinates"><LocateFixed size={14} /> {latitude.toFixed(4)}, {longitude.toFixed(4)}</span>
          </div>
          <div ref={mapNode} className="map-canvas" aria-label="Interactive location map" />
          <div className="map-scale-overlay" aria-hidden="true"><span />{(radiusM * 2 / 1000).toFixed(0)} km battlefield capture</div>
          <div className="map-presets">
            {presets.map((preset) => <button key={preset.label} onClick={() => moveTo(preset)}>{preset.label}</button>)}
            <button className="surprise-button" onClick={surpriseMe}><Shuffle size={13} /> Surprise me</button>
          </div>
          <span className="map-attribution">Map data © OpenStreetMap contributors</span>
        </div>

        <div className="mission-panel">
          <div className="mission-form">
            <div className="selection-status">
              <span>EARTH SELECTION</span>
              <strong>{selectedPlace}</strong>
              <small>{(radiusM * 2 / 1000).toFixed(0)} km footprint · {(radiusM * 2 / size).toFixed(0)} m per cell</small>
            </div>
            <label>
              Mission title
              <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={80} />
            </label>
            <label>
              Fictional premise
              <textarea value={story} onChange={(event) => setStory(event.target.value)} rows={3} maxLength={240} />
            </label>
            <div className="mission-selectors">
              <label>
                Map size
                <select value={size} onChange={(event) => { setSize(Number(event.target.value) as 64 | 96 | 128); clearGeneratedMission(); }}>
                  <option value={64}>64 × 64 · Quick</option>
                  <option value={96}>96 × 96 · Standard</option>
                  <option value={128}>128 × 128 · Epic</option>
                </select>
              </label>
              <label>
                Earth footprint
                <select value={radiusM} onChange={(event) => { setRadiusM(Number(event.target.value)); clearGeneratedMission(); }}>
                  <option value={2000}>4 km · Local</option>
                  <option value={3500}>7 km · District</option>
                  <option value={6000}>12 km · Regional</option>
                </select>
              </label>
            </div>
            <div className="variation-control">
              <label className="variation-copy" htmlFor="mission-seed">
                <span>Variation seed</span>
                <small>Same seed reproduces the same terrain</small>
              </label>
              <input id="mission-seed" type="number" min={0} max={2147483647} value={seed} onChange={(event) => { setSeed(Number(event.target.value) || 0); clearGeneratedMission(); }} />
              <button type="button" className="reroll-button" onClick={rerollSeed}><Shuffle size={14} /> Reroll</button>
            </div>
            <div className="generation-actions">
              <button className="generate-button" onClick={() => void generate()} disabled={authLoading || status === "acquiring" || status === "compiling"}>
                {status === "acquiring" || status === "compiling" ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
                {status === "acquiring" ? "Reading roads & water…" : status === "compiling" ? "Compiling OpenRA map…" : "Generate mission package"}
              </button>
              {(status === "acquiring" || status === "compiling") && <button className="cancel-generation" onClick={cancelGeneration}><X size={15} /> Cancel</button>}
            </div>
            {!authLoading && !user && <button type="button" className="generation-auth-note" onClick={() => openAuth("Create an account to generate and validate this battlefield")}><span>Account required for AI work</span><b>Sign in or create a free profile →</b></button>}
            {error && <p className="studio-error" role="alert">{error}</p>}
            <div className="generation-pipeline" aria-live="polite" aria-label="Mission generation pipeline">
              {["Pin Earth", "Read geometry", "Build terrain", "Validate map"].map((label, index) => (
                <span key={label} className={status === "ready" || pipelineStep > index + 1 ? "complete" : pipelineStep === index + 1 ? "active" : ""}>
                  <i>{status === "ready" || pipelineStep > index + 1 ? <Check size={12} /> : index + 1}</i><b>{label}</b>
                </span>
              ))}
            </div>
          </div>

          {mission ? (
            <div className="mission-result" aria-live="polite">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={mission.previewUrl} alt={`Generated terrain preview for ${title}`} />
              <div className="result-copy">
                <div className="result-topline"><span className="result-ready"><Check size={15} /> Playability checks passed</span><span className={`source-badge ${mission.sourceStatus === "live-openstreetmap" ? "live" : "fallback"}`}>{mission.sourceStatus === "live-openstreetmap" ? "Live Earth data" : "Resilient fallback"}</span></div>
                <h3>{mission.filename}</h3>
                <p>{mission.sourceStatus === "live-openstreetmap" ? `${mission.roadFeatureCount} road lines and ${mission.waterFeatureCount} waterways translated from OpenStreetMap in ${(generationMs / 1000).toFixed(1)}s.` : `Earth data timed out, so a deterministic, passable layout was compiled in ${(generationMs / 1000).toFixed(1)}s.`}</p>
                <div className="result-stats">
                  <span>{size}²<small>battlefield</small></span>
                  <span>{mission.sourceFeatureCount}<small>earth features</small></span>
                  <span>{mission.validation.length}/{mission.validation.length}<small>checks</small></span>
                </div>
                <ul className="validation-list">{mission.validation.map((check) => <li key={check}><Check size={11} />{check}</li>)}</ul>
                <div className="result-actions">
                  <a className="download-button" href={mission.downloadUrl} download={mission.filename} onClick={() => void trackAnalyticsEvent("mission_download", { map_size: size, source: mission.sourceStatus })}><Download size={17} /> Download .oramap</a>
                  <button onClick={() => void copyBlueprint()}><Share2 size={14} />{shareStatus === "copied" ? "Link copied" : shareStatus === "error" ? "Copy failed" : "Share setup"}</button>
                  <button onClick={generateVariation}><RefreshCw size={14} />New variation</button>
                </div>
                <small className="install-note">Already have the Windows alpha? Drag this file onto <b>Play-OpenRAAI.cmd</b>. <a href={windowsRelease.url} data-analytics-event="game-download" data-platform="windows-x64">Get the game bundle.</a></small>
              </div>
            </div>
          ) : (
            <div className="mission-placeholder">
              <MapPin size={20} />
              <div><strong>Your playable preview appears here.</strong><span>Earth geometry · routes · spawns · resources · validation</span></div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
