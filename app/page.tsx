import {
  Apple,
  ArrowRight,
  BrainCircuit,
  CalendarDays,
  CheckCircle2,
  Download,
  FileArchive,
  Github,
  Map,
  Mic2,
  MonitorDown,
  RadioTower,
  ShieldCheck,
  Sparkles,
  VolumeX,
  Zap,
} from "lucide-react";
import Image from "next/image";
import { MissionStudio } from "./components/MissionStudio";
import { CompanionDemo } from "./components/CompanionDemo";
import { AccountNav } from "./components/AccountNav";
import { getGameRelease } from "../lib/release";

const gameSource = "https://github.com/alibad/OpenRA-AI";
const canonicalUrl = "https://rtsai.net";

function Brand({ footer = false }: { footer?: boolean }) {
  return (
    <a className="brand" href="#top" aria-label="RTS AI home">
      <Image className="brand-symbol" src="/brand/rtsai-mark-64.png" alt="" width={34} height={34} priority={!footer} />
      <span className="brand-wordmark">RTS <b>AI</b>{!footer && <small>Playable intelligence</small>}</span>
    </a>
  );
}

function formatBytes(bytes: number | null) {
  if (!bytes) return null;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string | null) {
  if (!value) return "Verified release";
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

export default async function Home() {
  const gameRelease = await getGameRelease();
  const windowsRelease = gameRelease.windows;
  const primaryWindowsUrl = windowsRelease.installerUrl ?? windowsRelease.url;
  const primaryWindowsSize = formatBytes(windowsRelease.installerSizeBytes ?? windowsRelease.sizeBytes);
  const appleSiliconRelease = gameRelease.macos?.assets.find((asset) => asset.architecture === "arm64");
  const intelMacRelease = gameRelease.macos?.assets.find((asset) => asset.architecture === "x64");
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": `${canonicalUrl}/#website`,
        url: canonicalUrl,
        name: "RTS AI",
        description: "An AI companion and Earth mission generator for OpenRA.",
        inLanguage: "en",
      },
      {
        "@type": ["SoftwareApplication", "VideoGame"],
        "@id": `${canonicalUrl}/#openra-ai`,
        name: "OpenRA AI",
        url: canonicalUrl,
        description: "A playable OpenRA build with an interruptible AI companion and real-world mission generation.",
        applicationCategory: "GameApplication",
        operatingSystem: gameRelease.macos ? "Windows 10, Windows 11, macOS" : "Windows 10, Windows 11",
        softwareVersion: windowsRelease.version,
        downloadUrl: primaryWindowsUrl,
        isAccessibleForFree: true,
        image: `${canonicalUrl}/social-card.png`,
        sameAs: [gameSource],
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: "USD",
          url: primaryWindowsUrl,
        },
      },
    ],
  };

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <nav className="site-nav" aria-label="Primary navigation">
        <Brand />
        <div className="nav-links">
          <a href="#companion">Companion</a>
          <a href="#mission-studio">Mission studio</a>
          <a href="#download">Download</a>
          <a href="#architecture">How it works</a>
        </div>
        <div className="nav-actions"><a className="nav-source" href={gameSource} target="_blank" rel="noreferrer"><Github size={15} /> Game source</a><AccountNav /></div>
      </nav>

      <p className="legal-strip">Independent project. EA has not endorsed and does not support this product.</p>

      <main id="main-content">
      <header className="hero" id="top">
        <div className="hero-radar" aria-hidden="true"><i /><i /><i /><span /></div>
        <div className="hero-copy">
          <span className="eyebrow"><span className="live-dot" /> Independent / playable alpha</span>
          <h1>Your battlefield.<br /><em>Now it talks back.</em></h1>
          <p className="hero-lede">A quiet AI companion for OpenRA—and a map generator that turns any place on Earth into a fictional, playable skirmish.</p>
          <div className="hero-actions">
            <a className="primary-action" href="#download"><Download size={17} /> Download the game</a>
            <a className="text-action" href="#mission-studio">Build a mission <ArrowRight size={17} /></a>
          </div>
          <div className="hero-proof">
            <span><ShieldCheck size={15} /> Observation-only</span>
            <span><VolumeX size={15} /> Interruptible</span>
            <span><Zap size={15} /> AI-layer routed</span>
          </div>
        </div>
        <CompanionDemo />
      </header>

      <div className="capability-rail" aria-label="Core capabilities">
        <span>01 <b>Notices what matters</b></span>
        <span>02 <b>Answers about this match</b></span>
        <span>03 <b>Reads real Earth geometry</b></span>
        <span>04 <b>Validates every .oramap</b></span>
      </div>

      <section className="download-section" id="download" aria-labelledby="download-title">
        <div className="download-intro">
          <span className="section-number">PLAYABLE BUILD / {windowsRelease.version}</span>
          <h2 id="download-title">Install. Launch. Command.</h2>
          <p>Every build carries the game engine, AI companion, launcher, and a playable Earth-derived skirmish. Choose a native setup or keep the portable package.</p>
          <div className="release-trust" aria-label="Release details">
            <span><CheckCircle2 size={15} /> Locally built and smoke-tested</span>
            <span><CalendarDays size={15} /> Released {formatDate(windowsRelease.publishedAt)}</span>
          </div>
        </div>

        <div className="platform-downloads" aria-label="Platform downloads">
          <article className="platform-card is-ready">
            <div className="platform-card-heading">
              <span className="platform-icon"><MonitorDown size={23} /></span>
              <div><span className="platform-kicker">Windows 10 / 11</span><h3>Windows x64</h3></div>
              <span className="release-status is-ready">Ready</span>
            </div>
            <p>A normal per-user setup with the RTS AI app icon, Start menu entry, desktop shortcut, and uninstaller.</p>
            <a className="primary-action platform-primary" href={primaryWindowsUrl} data-analytics-event="game-download" data-platform="windows-x64-setup"><Download size={17} /> Download Windows setup</a>
            <div className="platform-meta">
              <span>{primaryWindowsSize ?? "Setup executable"}</span>
              {windowsRelease.installerChecksumUrl && <a href={windowsRelease.installerChecksumUrl}>Setup checksum</a>}
              <a href={windowsRelease.url} data-analytics-event="game-download" data-platform="windows-x64-portable">Portable ZIP</a>
              <a href={windowsRelease.checksumUrl}>ZIP checksum</a>
            </div>
          </article>

          <article className={`platform-card ${gameRelease.macos ? "is-ready" : "is-pending"}`}>
            <div className="platform-card-heading">
              <span className="platform-icon"><Apple size={23} /></span>
              <div><span className="platform-kicker">Apple desktop</span><h3>macOS</h3></div>
              <span className={`release-status ${gameRelease.macos ? "is-ready" : "is-pending"}`}>{gameRelease.macos ? "Ready" : "Signing"}</span>
            </div>
            {gameRelease.macos ? (
              <>
                <p>A native signed disk image. Choose the build that matches your Mac.</p>
                <div className="mac-download-actions">
                  {appleSiliconRelease && <a className="primary-action platform-primary" href={appleSiliconRelease.url} data-analytics-event="game-download" data-platform="macos-arm64"><Download size={17} /> Apple silicon</a>}
                  {intelMacRelease && <a className="secondary-download" href={intelMacRelease.url} data-analytics-event="game-download" data-platform="macos-x64">Intel Mac</a>}
                </div>
                <div className="platform-meta">
                  <span>Version {gameRelease.macos.version}</span>
                  {appleSiliconRelease?.checksumUrl && <a href={appleSiliconRelease.checksumUrl}>Apple silicon checksum</a>}
                  {intelMacRelease?.checksumUrl && <a href={intelMacRelease.checksumUrl}>Intel checksum</a>}
                </div>
              </>
            ) : (
              <>
                <p>The native app and DMG packaging path is complete. Its public download stays locked until the artifact is built, signed, and notarized on a Mac.</p>
                <span className="pending-download" aria-disabled="true">Signed macOS download pending</span>
                <div className="platform-meta"><span>Apple silicon + Intel pipeline</span><span>No placeholder download</span></div>
              </>
            )}
          </article>
        </div>

        <ol className="play-steps">
          <li><span>01</span><div><b>Install or extract</b><p>Use Windows setup for shortcuts and uninstall support, or keep the ZIP fully portable.</p></div></li>
          <li><span>02</span><div><b>Launch OpenRA AI</b><p>The first run verifies and downloads OpenRA&apos;s supported Red Alert content, then starts the generated map.</p></div></li>
          <li><span>03</span><div><b>Hold Ctrl+Space to ask</b><p>Release to hear the answer. Ctrl+Shift+M mutes; Ctrl+Shift+A disables or enables the companion.</p></div></li>
        </ol>
        <div className="download-footnote"><FileArchive size={15} /><span>Checksums are published beside every downloadable artifact. The model-backed companion expects your private AI layer on this machine; the game itself still runs if that layer is offline.</span></div>
      </section>

      <section className="companion-section" id="companion">
        <div className="section-intro">
          <span className="section-number">01 / COMPANION</span>
          <h2>Helpful enough to speak.<br />Quiet enough to keep.</h2>
          <p>The OpenRA AI companion watches structured game state—not a constant video feed. Deterministic rules decide whether something is worth your attention before a model is called.</p>
        </div>
        <div className="principles">
          <article>
            <RadioTower size={22} />
            <h3>Notices the change</h3>
            <p>New armor, a power deficit, a lost harvester, or a critically damaged unit—not a running commentary.</p>
            <span>Game event → relevance gate</span>
          </article>
          <article>
            <BrainCircuit size={22} />
            <h3>Respects fog of war</h3>
            <p>The model receives only the compact observation already visible to you. Hidden enemies stay hidden.</p>
            <span>Snapshot → AI layer → one line</span>
          </article>
          <article>
            <Mic2 size={22} />
            <h3>Yields instantly</h3>
            <p>Ask by voice, cut it off, mute it, or disable it. No modal panels and no AI-issued game orders.</p>
            <span>Speak · interrupt · continue playing</span>
          </article>
        </div>
      </section>

      <MissionStudio windowsRelease={windowsRelease} />

      <section className="architecture-section" id="architecture">
        <div className="architecture-copy">
          <span className="section-number">03 / BUILT TO EVOLVE</span>
          <h2>The experience stays stable.<br />The models can change.</h2>
          <p>The game never talks to a model provider directly. A private AI layer owns model credentials and named capabilities, so cloud models can be replaced by local ones later without rewriting the OpenRA integration.</p>
          <a href={gameSource} target="_blank" rel="noreferrer">Read the architecture <ArrowRight size={16} /></a>
        </div>
        <div className="route-diagram" aria-label="AI routing architecture">
          <div><Map size={18} /><span>OpenRA engine<small>fog-respecting snapshot</small></span></div>
          <i />
          <div className="active-route"><Sparkles size={18} /><span>OpenRA AI<small>relevance + interruption</small></span></div>
          <i />
          <div><RadioTower size={18} /><span>AI layer<small>named model routes</small></span></div>
          <i />
          <div className="model-routes">
            <span>reasoning<small>provider or local model</small></span>
            <span>transcription<small>voice input route</small></span>
            <span>speech<small>spoken response route</small></span>
          </div>
        </div>
      </section>

      <section className="closing-section">
        <div>
          <span className="eyebrow">Built in the open</span>
          <h2>Pick a place.<br />Start a story.</h2>
        </div>
        <div>
          <p>Generate a mission now or install the tested Windows alpha. The same download surface will expose macOS automatically when its signed DMG is released.</p>
          <div className="hero-actions">
            <a className="primary-action" href={primaryWindowsUrl} data-analytics-event="game-download" data-platform="windows-x64-setup"><Download size={17} /> Download Windows setup</a>
            <a className="text-action" href="#mission-studio">Open mission studio <ArrowRight size={17} /></a>
          </div>
        </div>
      </section>
      </main>

      <footer>
        <Brand footer />
        <p>EA has not endorsed and does not support this product. OpenRA AI is an independent GPL-3.0 project.</p>
        <div><a href={gameSource}>Game source</a><a href={`${gameSource}/blob/main/LICENSE`}>License</a><a href="/privacy">Privacy</a><a href="https://www.openstreetmap.org/copyright">Map attribution</a></div>
      </footer>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }}
      />
    </>
  );
}
