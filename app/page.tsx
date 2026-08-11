import { ArrowRight, BrainCircuit, Download, Globe2, ShieldCheck, VolumeX, Zap } from "lucide-react";
import Link from "next/link";
import { CompanionDemo } from "./components/CompanionDemo";
import { CurrentShowcase } from "./components/CurrentShowcase";
import { gameSource, SiteFooter, SiteHeader } from "./components/SiteChrome";
import { getGameRelease } from "../lib/release";
import { productLayers } from "../lib/product-plan";

const canonicalUrl = "https://rtsai.net";
const experienceIcons = { companion: BrainCircuit, world: Globe2 };

export default async function Home() {
  const gameRelease = await getGameRelease();
  const windowsRelease = gameRelease.windows;
  const primaryWindowsUrl = windowsRelease.installerUrl ?? windowsRelease.url;
  const coreExperiences = productLayers.filter((layer) => layer.id !== "distribution");
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": `${canonicalUrl}/#website`,
        url: canonicalUrl,
        name: "RTS AI",
        description: "An AI-native RTS platform for intelligent play and Earth-built missions.",
        inLanguage: "en",
      },
      {
        "@type": ["SoftwareApplication", "VideoGame"],
        "@id": `${canonicalUrl}/#openra-ai`,
        name: "OpenRA AI",
        url: canonicalUrl,
        description: "A playable OpenRA build with an interruptible AI companion, optional AUTO delegation, and real-world mission generation.",
        applicationCategory: "GameApplication",
        operatingSystem: gameRelease.macos ? "Windows 10, Windows 11, macOS" : "Windows 10, Windows 11",
        softwareVersion: windowsRelease.version,
        downloadUrl: primaryWindowsUrl,
        isAccessibleForFree: true,
        image: `${canonicalUrl}/social-card.png`,
        sameAs: [gameSource],
        offers: { "@type": "Offer", price: "0", priceCurrency: "USD", url: primaryWindowsUrl },
      },
    ],
  };

  return (
    <>
      <SiteHeader />
      <main id="main-content">
        <header className="hero" id="top">
          <div className="hero-radar" aria-hidden="true"><i /><i /><i /><span /></div>
          <div className="hero-copy">
            <Link className="eyebrow hero-release-link" href="/platform"><span className="live-dot" /> Playable alpha / built as a platform <ArrowRight size={13} /></Link>
            <h1>Your battlefield.<br /><em>Now it talks back.</em></h1>
            <p className="hero-lede">OpenRA rebuilt around human + AI play: an interruptible companion in the match and a mission studio that turns real places into playable battlefields.</p>
            <div className="hero-actions">
              <Link className="primary-action" href="/download"><Download size={17} /> Download the game</Link>
              <Link className="text-action" href="/studio">Build a mission <ArrowRight size={17} /></Link>
            </div>
            <div className="hero-proof">
              <span><ShieldCheck size={15} /> Fog-respecting</span>
              <span><VolumeX size={15} /> Interruptible</span>
              <span><Zap size={15} /> AUTO is optional</span>
            </div>
          </div>
          <CompanionDemo />
        </header>

        <div className="capability-rail home-capability-rail" aria-label="Core capabilities">
          <span>01 <b>Play with intelligence</b></span>
          <span>02 <b>Create from Earth</b></span>
          <span>03 <b>Download and launch</b></span>
        </div>

        <section className="home-experiences" aria-labelledby="experiences-title">
          <div className="home-section-heading">
            <span className="section-number">TWO CORE EXPERIENCES</span>
            <h2 id="experiences-title">Intelligence inside the match.<br />The world outside it.</h2>
            <p>Start with the way you want to play. Both experiences meet in the same native OpenRA build.</p>
          </div>
          <div className="home-experience-grid">
            {coreExperiences.map((experience) => {
              const ExperienceIcon = experienceIcons[experience.id as keyof typeof experienceIcons];
              const href = experience.id === "companion" ? "/companion" : "/studio";
              return (
                <Link href={href} className="home-experience-card" key={experience.id}>
                  <div><span>{experience.number}</span><i>{experience.status}</i></div>
                  <ExperienceIcon size={26} />
                  <h3>{experience.title}</h3>
                  <p>{experience.description}</p>
                  <strong>Explore the experience <ArrowRight size={16} /></strong>
                </Link>
              );
            })}
          </div>
        </section>

        <section className="home-proof" aria-labelledby="proof-title">
          <div className="home-section-heading home-proof-heading">
            <span className="section-number">CURRENT PLAYABLE PROOF</span>
            <h2 id="proof-title">Not a concept.<br />A battlefield you can launch.</h2>
            <Link href="/platform">See the full platform plan <ArrowRight size={16} /></Link>
          </div>
          <CurrentShowcase downloadUrl={primaryWindowsUrl} version={windowsRelease.version} compact />
        </section>

        <section className="closing-section home-closing">
          <div>
            <span className="eyebrow">Free playable alpha</span>
            <h2>Install the game.<br />Bring the AI.</h2>
          </div>
          <div>
            <p>Download the verified Windows build, check macOS availability, or open the Earth studio and create a mission package first.</p>
            <div className="hero-actions">
              <Link className="primary-action" href="/download"><Download size={17} /> Choose your download</Link>
              <Link className="text-action" href="/studio">Open Earth studio <ArrowRight size={17} /></Link>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }} />
    </>
  );
}
