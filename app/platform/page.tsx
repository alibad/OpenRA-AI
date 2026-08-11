import type { Metadata } from "next";
import { Blocks, Bot, BrainCircuit, Globe2, MonitorDown } from "lucide-react";
import { CurrentShowcase } from "../components/CurrentShowcase";
import { SiteFooter, SiteHeader } from "../components/SiteChrome";
import { currentShowcase, developmentTracks, productLayers } from "../../lib/product-plan";
import { getWindowsRelease } from "../../lib/release";

export const metadata: Metadata = {
  title: "Platform Plan | RTS AI",
  description: "See how the AI companion, Earth mission studio, distribution layer, new theatres, and autonomous strategy research fit together.",
  alternates: { canonical: "/platform" },
};

const productLayerIcons = { companion: BrainCircuit, world: Globe2, distribution: MonitorDown };
const developmentTrackIcons = { creation: Blocks, autonomy: Bot };

export default async function PlatformPage() {
  const windowsRelease = await getWindowsRelease();
  return (
    <>
      <SiteHeader />
      <main id="main-content">
        <header className="route-hero">
          <span className="eyebrow">THE RTS AI PLATFORM</span>
          <h1>One foundation.<br /><em>More ways to play.</em></h1>
          <p>The companion and Earth mission studio are the core experiences. Distribution, new theatres, and bounded autonomous agents make them easier to reach and stronger over time.</p>
        </header>
        <section className="platform-shell" aria-labelledby="platform-title">
          <div className="platform-vision">
            <div className="platform-heading">
              <span className="section-number">THE PRODUCT PLAN</span>
              <h2 id="platform-title">Two core experiences.<br />One way in.</h2>
              <p>The plan remains an AI game companion, an Earth-to-Mission generator, and a web + launcher surface that makes both approachable. New mods and autonomous agents grow from that foundation; they do not replace it.</p>
            </div>
            <div className="product-layers" aria-label="RTS AI product layers">
              {productLayers.map((layer) => {
                const LayerIcon = productLayerIcons[layer.id];
                return <article key={layer.id}><div className="product-layer-top"><span>{layer.number}</span><i>{layer.status}</i></div><LayerIcon size={21} /><h3>{layer.title}</h3><p>{layer.description}</p><small>{layer.outcome}</small></article>;
              })}
            </div>
            <div className="development-tracks" aria-label="Platform development tracks">
              {developmentTracks.map((track) => {
                const TrackIcon = developmentTrackIcons[track.id];
                return <article key={track.id}><TrackIcon size={18} /><span>{track.label}</span><div><b>{track.title}</b><p>{track.description}</p></div></article>;
              })}
            </div>
            <CurrentShowcase downloadUrl={windowsRelease.installerUrl ?? windowsRelease.url} version={windowsRelease.version} />
            <p className="showcase-context">The current showcase is {currentShowcase.title}. The platform plan is deliberately release-agnostic so the next theatre can replace it without rewriting the product story.</p>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
