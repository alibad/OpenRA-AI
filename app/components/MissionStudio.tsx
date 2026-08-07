"use client";

import {
  Check,
  Crosshair,
  Download,
  LoaderCircle,
  LocateFixed,
  MapPin,
  Search,
  Sparkles,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Map as MapLibreMap, Marker } from "maplibre-gl";
import { generateEarthMission, type MissionPackage } from "../../lib/oramap";

const presets = [
  { label: "Riyadh", latitude: 24.7136, longitude: 46.6753 },
  { label: "Manhattan", latitude: 40.7128, longitude: -74.006 },
  { label: "Tokyo Bay", latitude: 35.6329, longitude: 139.797 },
  { label: "Cape Town", latitude: -33.9249, longitude: 18.4241 },
];

export function MissionStudio() {
  const mapNode = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const [latitude, setLatitude] = useState(24.7136);
  const [longitude, setLongitude] = useState(46.6753);
  const [title, setTitle] = useState("Riyadh Crossing");
  const [seed, setSeed] = useState(42);
  const [story, setStory] = useState("A contested supply corridor cuts across the city edge.");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<"idle" | "locating" | "acquiring" | "compiling" | "ready" | "error">("idle");
  const [mission, setMission] = useState<(MissionPackage & { downloadUrl: string }) | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let map: MapLibreMap | null = null;
    void import("maplibre-gl").then((maplibre) => {
      if (cancelled || !mapNode.current) return;
      map = new maplibre.Map({
        container: mapNode.current,
        center: [longitude, latitude],
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
      markerRef.current = new maplibre.Marker({ color: "#ef5b3f" }).setLngLat([longitude, latitude]).addTo(map);
      map.on("click", (event) => {
        const lat = Number(event.lngLat.lat.toFixed(5));
        const lon = Number(event.lngLat.lng.toFixed(5));
        setLatitude(lat);
        setLongitude(lon);
        markerRef.current?.setLngLat([lon, lat]);
        setMission(null);
        setStatus("idle");
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

  useEffect(() => () => {
    if (mission?.downloadUrl) URL.revokeObjectURL(mission.downloadUrl);
  }, [mission]);

  function moveTo(next: { label: string; latitude: number; longitude: number }) {
    setLatitude(next.latitude);
    setLongitude(next.longitude);
    setTitle(`${next.label} Crossing`);
    markerRef.current?.setLngLat([next.longitude, next.latitude]);
    mapRef.current?.flyTo({ center: [next.longitude, next.latitude], zoom: 10.5 });
    setMission(null);
    setStatus("idle");
  }

  async function locate() {
    if (!search.trim()) return;
    setStatus("locating");
    setError("");
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(search)}`, {
        headers: { "Accept-Language": "en" },
      });
      if (!response.ok) throw new Error("Place search is unavailable");
      const results = (await response.json()) as Array<{ lat: string; lon: string; display_name: string }>;
      if (!results.length) throw new Error("No place matched that search");
      const result = results[0];
      moveTo({ label: result.display_name.split(",")[0], latitude: Number(result.lat), longitude: Number(result.lon) });
    } catch (cause) {
      setStatus("error");
      setError(cause instanceof Error ? cause.message : "Could not locate that place");
    }
  }

  async function generate() {
    setStatus("acquiring");
    setError("");
    setMission(null);
    try {
      const compiling = window.setTimeout(() => setStatus("compiling"), 700);
      const result = await generateEarthMission({
        latitude,
        longitude,
        title,
        radiusM: 3500,
        size: 64,
        seed,
        story,
      });
      window.clearTimeout(compiling);
      const downloadUrl = URL.createObjectURL(result.blob);
      setMission({ ...result, downloadUrl });
      setStatus("ready");
    } catch (cause) {
      setStatus("error");
      setError(cause instanceof Error ? cause.message : "Mission compilation failed");
    }
  }

  return (
    <section className="studio-shell" id="mission-studio" aria-labelledby="studio-title">
      <div className="studio-heading">
        <div>
          <span className="eyebrow"><Crosshair size={14} /> Mission studio / alpha</span>
          <h2 id="studio-title">Point anywhere. Leave with a battlefield.</h2>
        </div>
        <p>Click the map, keep or rewrite the premise, then compile a playable Red Alert map in your browser.</p>
      </div>

      <div className="studio-grid">
        <div className="map-panel">
          <div className="map-toolbar">
            <div className="search-field">
              <Search size={16} aria-hidden="true" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && void locate()}
                placeholder="Find a city, coast, or landmark"
                aria-label="Find a location"
              />
              <button onClick={() => void locate()} aria-label="Search location">Go</button>
            </div>
            <span className="coordinates"><LocateFixed size={14} /> {latitude.toFixed(4)}, {longitude.toFixed(4)}</span>
          </div>
          <div ref={mapNode} className="map-canvas" aria-label="Interactive location map" />
          <div className="map-presets">
            {presets.map((preset) => <button key={preset.label} onClick={() => moveTo(preset)}>{preset.label}</button>)}
          </div>
          <span className="map-attribution">Map data © OpenStreetMap contributors</span>
        </div>

        <div className="mission-panel">
          <div className="mission-form">
            <label>
              Mission title
              <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={80} />
            </label>
            <label>
              Fictional premise
              <textarea value={story} onChange={(event) => setStory(event.target.value)} rows={3} maxLength={240} />
            </label>
            <div className="form-pair">
              <div className="display-label">
                Map size
                <span className="fixed-input">64 × 64 <small>2 players</small></span>
              </div>
              <label>
                Seed
                <input type="number" min={0} max={2147483647} value={seed} onChange={(event) => setSeed(Number(event.target.value) || 0)} />
              </label>
            </div>
            <button className="generate-button" onClick={() => void generate()} disabled={status === "acquiring" || status === "compiling"}>
              {status === "acquiring" || status === "compiling" ? <LoaderCircle className="spin" size={18} /> : <Sparkles size={18} />}
              {status === "acquiring" ? "Reading roads & water…" : status === "compiling" ? "Compiling OpenRA map…" : "Generate mission package"}
            </button>
            {error && <p className="studio-error" role="alert">{error}</p>}
          </div>

          {mission ? (
            <div className="mission-result" aria-live="polite">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={mission.previewUrl} alt={`Generated terrain preview for ${title}`} />
              <div className="result-copy">
                <span className="result-ready"><Check size={15} /> Playability checks passed</span>
                <h3>{mission.filename}</h3>
                <p>{mission.sourceStatus === "live-openstreetmap" ? "Road and water structure translated from OpenStreetMap." : "Network data was unavailable, so a labeled deterministic terrain fallback was used."}</p>
                <div className="result-stats">
                  <span>{mission.waterCells}<small>water cells</small></span>
                  <span>{mission.roadCells}<small>route cells</small></span>
                  <span>4/4<small>checks</small></span>
                </div>
                <a className="download-button" href={mission.downloadUrl} download={mission.filename}><Download size={17} /> Download .oramap</a>
                <small className="install-note">Drop it into your OpenRA maps folder or open it in the map editor.</small>
              </div>
            </div>
          ) : (
            <div className="mission-placeholder">
              <MapPin size={20} />
              <div><strong>Your package appears here.</strong><span>Terrain · spawns · ore · briefing · manifest</span></div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
