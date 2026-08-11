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
const redSeaDocs = `${gameSource}/blob/main/docs/red-sea-2026.md`;
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
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
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
  const aiPackSize = formatBytes(windowsRelease.aiPackSizeBytes);
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
        description: "An AI-powered OpenRA build with delegated play, Earth mission generation, and the Red Sea 2026 prototype.",
        inLanguage: "en",
      },
      {
        "@type": ["SoftwareApplication", "VideoGame"],
        "@id": `${canonicalUrl}/#openra-ai`,
        name: "OpenRA AI",
        url: canonicalUrl,
        description: "A playable OpenRA build with an interruptible AI companion, optional AUTO delegation, real-world mission generation, and Red Sea 2026.",
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
          <a href="#red-sea-2026">Red Sea 2026</a>
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
          <a className="eyebrow hero-release-link" href="#red-sea-2026"><span className="live-dot" /> Alpha.9 live / Red Sea 2026 included <ArrowRight size={13} /></a>
          <h1>Your battlefield.<br /><em>Now it talks back.</em></h1>
          <p className="hero-lede">An interruptible OpenRA companion that can advise, execute confirmed actions, or take optional AUTO command—plus Earth-built missions and the new Red Sea 2026 prototype.</p>
          <div className="hero-actions">
            <a className="primary-action" href="#download"><Download size={17} /> Download the game</a>
            <a className="text-action" href="#mission-studio">Build a mission <ArrowRight size={17} /></a>
          </div>
          <div className="hero-proof">
            <span><ShieldCheck size={15} /> Fog-respecting</span>
            <span><VolumeX size={15} /> Interruptible</span>
            <span><Zap size={15} /> AUTO is optional</span>
          </div>
        </div>
        <CompanionDemo />
      </header>

      <div className="capability-rail" aria-label="Core capabilities">
        <span>01 <b>Notices what matters</b></span>
        <span>02 <b>Answers about this match</b></span>
        <span>03 <b>Acts only when authorized</b></span>
        <span>04 <b>Builds from real Earth</b></span>
      </div>

      <section className="download-section" id="download" aria-labelledby="download-title">
        <div className="download-intro">
          <span className="section-number">PLAYABLE BUILD / {windowsRelease.version}</span>
          <h2 id="download-title">Install. Launch. Command.</h2>
          <p>Alpha.9 carries the engine, companion, AUTO strategy layer, Earth tools, and Red Sea 2026 prototype. Choose a native setup or keep the portable package.</p>
          <div className="release-trust" aria-label="Release details">
            <span><CheckCircle2 size={15} /> Locally built and smoke-tested</span>
            <span><CalendarDays size={15} /> Released {formatDate(windowsRelease.publishedAt)}</span>
            <a href="#red-sea-2026"><Sparkles size={15} /> New: Saudi Arabia + Yemen</a>
          </div>
        </div>

        <div className="platform-downloads" aria-label="Platform downloads">
          <article className="platform-card is-ready">
            <div className="platform-card-heading">
              <span className="platform-icon"><MonitorDown size={23} /></span>
              <div><span className="platform-kicker">Windows 10 / 11</span><h3>Windows x64</h3></div>
              <span className="release-status is-ready">Ready</span>
            </div>
            <p>A normal per-user setup with the RTS AI app icon, Start menu entry, desktop shortcut, uninstaller, and the Red Sea launch script.</p>
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

        {windowsRelease.aiPackUrl && (
          <div className="ai-pack-callout">
            <span className="platform-icon"><BrainCircuit size={22} /></span>
            <div><b>Optional Local AI Pack</b><p>Qwen3-VL, Whisper, and Kokoro—the pinned model payload for private local vision, transcription, and speech.</p></div>
            <span>{aiPackSize ?? "Model bundle"}</span>
            <a href={windowsRelease.aiPackUrl} data-analytics-event="ai-pack-download" data-platform="windows-x64"><Download size={15} /> Download AI Pack</a>
            {windowsRelease.aiPackChecksumUrl && <a className="checksum-link" href={windowsRelease.aiPackChecksumUrl}>Checksum</a>}
          </div>
        )}

        <ol className="play-steps">
          <li><span>01</span><div><b>Install or extract</b><p>Use Windows setup for shortcuts and uninstall support, or keep the ZIP fully portable.</p></div></li>
          <li><span>02</span><div><b>Choose your battlefield</b><p>Launch OpenRA AI normally, or run <code>Play-Red-Sea-2026.cmd</code> to build and open Jizan Corridor.</p></div></li>
          <li><span>03</span><div><b>Hold Ctrl+Space to ask</b><p>Release to hear the answer. Ctrl+Shift+M mutes; Ctrl+Shift+A disables or enables the companion.</p></div></li>
        </ol>
        <div className="download-footnote"><FileArchive size={15} /><span>Checksums are published beside every downloadable artifact. The model-backed companion expects your private AI layer on this machine; the game itself still runs if that layer is offline.</span></div>
      </section>

      <section className="red-sea-shell" id="red-sea-2026" aria-labelledby="red-sea-title">
        <div className="red-sea-section">
          <div className="red-sea-visual">
            <Image src="/red-sea-2026-key-art.webp" alt="Red Sea coastal battlefield concept featuring armor, air defense, drones, and a relief ship" width={1600} height={900} sizes="(max-width: 1050px) 100vw, 58vw" />
            <span className="red-sea-release-tag"><i /> Included in Alpha.9</span>
            <div className="red-sea-readout"><span>FIRST CONTRACT</span><b>Jizan Corridor</b><small>Earth-derived · validated · playable</small></div>
          </div>
          <div className="red-sea-copy">
            <span className="section-number">NEW MOD PROTOTYPE / RED SEA 2026</span>
            <h2 id="red-sea-title">New countries.<br />A new theatre.</h2>
            <p>Saudi Arabia and Yemen join the Red Alert country selector with faction-gated units, native bot production priorities, and a source-dated Earth mission contract.</p>
            <div className="faction-roster" aria-label="Red Sea 2026 faction roster">
              <article><span>SA</span><div><b>Saudi Arabia</b><p>M1A2S main battle tank<br />Mobile air defense system</p></div></article>
              <article><span>YE</span><div><b>Yemen</b><p>Armed technical · missile launcher<br />Samad drone</p></div></article>
            </div>
            <div className="mission-contract">
              <Map size={19} />
              <div><span>PLAYABLE EARTH CONTRACT</span><b>Jizan Corridor</b><p>The dedicated launcher generates, validates, installs, and opens the battlefield. The prototype lives inside Red Alert while the standalone expansion shell is developed.</p></div>
            </div>
            <div className="red-sea-actions">
              <a className="primary-action" href={primaryWindowsUrl} data-analytics-event="game-download" data-platform="red-sea-windows"><Download size={17} /> Play on Windows</a>
              <a className="text-action" href={redSeaDocs} target="_blank" rel="noreferrer">Read the field brief <ArrowRight size={16} /></a>
            </div>
          </div>
        </div>
      </section>

      <section className="companion-section" id="companion">
        <div className="section-intro">
          <span className="section-number">02 / COMPANION + COMMAND</span>
          <h2>Helpful enough to speak.<br />Safe enough to act.</h2>
          <p>The companion combines deterministic game state with fog-respecting tactical views. It can explain, propose a safe order for confirmation, or delegate real-time play to OpenRA&apos;s native bot stack when AUTO is explicitly enabled.</p>
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
            <h3>You retain command</h3>
            <p>Confirm individual actions, switch strategies by voice, or turn AUTO on. Interrupt speech or disable delegation at any moment.</p>
            <span>Ask · confirm · delegate · take back</span>
          </article>
        </div>
      </section>

      <MissionStudio windowsRelease={windowsRelease} />

      <section className="architecture-section" id="architecture">
        <div className="architecture-copy">
          <span className="section-number">04 / BUILT TO EVOLVE</span>
          <h2>The experience stays stable.<br />The models can change.</h2>
          <p>The game never talks to a model provider directly. A private AI layer owns model credentials and named capabilities, while deterministic OpenRA logic keeps economy, production, combat, and AUTO play moving without waiting on an LLM.</p>
          <a href={gameSource} target="_blank" rel="noreferrer">Read the architecture <ArrowRight size={16} /></a>
        </div>
        <div className="route-diagram" aria-label="AI routing architecture">
          <div><Map size={18} /><span>OpenRA engine<small>fog-respecting snapshot</small></span></div>
          <i />
          <div className="active-route"><Sparkles size={18} /><span>OpenRA AI<small>relevance + safe actions</small></span></div>
          <i />
          <div><RadioTower size={18} /><span>AI layer<small>named model routes</small></span></div>
          <i />
          <div className="model-routes">
            <span>strategy<small>provider or local model</small></span>
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
          <p>Generate a mission, enter Jizan Corridor, or install the tested Windows alpha. The same download surface will expose macOS automatically when its signed DMG is released.</p>
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
