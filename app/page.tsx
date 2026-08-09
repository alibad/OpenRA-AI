import {
  ArrowRight,
  BrainCircuit,
  CalendarDays,
  CheckCircle2,
  Download,
  FileArchive,
  Github,
  Map,
  Mic2,
  RadioTower,
  ShieldCheck,
  Sparkles,
  VolumeX,
  Zap,
} from "lucide-react";
import { MissionStudio } from "./components/MissionStudio";
import { CompanionDemo } from "./components/CompanionDemo";
import { getWindowsRelease } from "../lib/release";

const gameSource = "https://github.com/alibad/OpenRA-AI";

function formatBytes(bytes: number | null) {
  if (!bytes) return null;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string | null) {
  if (!value) return "Verified release";
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

export default async function Home() {
  const windowsRelease = await getWindowsRelease();
  const releaseSize = formatBytes(windowsRelease.sizeBytes);
  return (
    <main>
      <nav className="site-nav" aria-label="Primary navigation">
        <a className="brand" href="#top" aria-label="RTS AI home">
          <span className="brand-mark">RTS</span>
          <span>RTS <b>AI</b></span>
        </a>
        <div className="nav-links">
          <a href="#companion">Companion</a>
          <a href="#mission-studio">Mission studio</a>
          <a href="#download">Download</a>
          <a href="#architecture">How it works</a>
        </div>
        <a className="nav-source" href={gameSource} target="_blank" rel="noreferrer"><Github size={15} /> Game source</a>
      </nav>

      <p className="legal-strip">Independent project. EA has not endorsed and does not support this product.</p>

      <header className="hero" id="top">
        <div className="hero-radar" aria-hidden="true"><i /><i /><i /><span /></div>
        <div className="hero-copy">
          <span className="eyebrow"><span className="live-dot" /> Independent / playable alpha</span>
          <h1>Your battlefield.<br /><em>Now it talks back.</em></h1>
          <p className="hero-lede">A quiet AI companion for OpenRA—and a map generator that turns any place on Earth into a fictional, playable skirmish.</p>
          <div className="hero-actions">
            <a className="primary-action" href="#download"><Download size={17} /> Download Windows alpha</a>
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
          <h2 id="download-title">From a ZIP to a live match.</h2>
          <p>The Windows alpha bundles the pinned engine, AI companion, launcher, and a generated Riyadh skirmish. No installer and no hosted workflow.</p>
          <div className="download-actions">
            <a className="primary-action" href={windowsRelease.url} data-analytics-event="game-download" data-platform="windows-x64"><Download size={17} /> Download for Windows x64</a>
            <a className="checksum-link" href={windowsRelease.checksumUrl}>SHA-256 checksum</a>
          </div>
          <div className="release-trust" aria-label="Release details">
            <span><CheckCircle2 size={15} /> Portable, checksum published</span>
            <span><CalendarDays size={15} /> Released {formatDate(windowsRelease.publishedAt)}</span>
          </div>
        </div>
        <ol className="play-steps">
          <li><span>01</span><div><b>Extract the ZIP</b><p>Keep the included folders together. The package is portable.</p></div></li>
          <li><span>02</span><div><b>Run Play-OpenRAAI.cmd</b><p>The first run verifies and downloads OpenRA&apos;s supported Red Alert content, then starts the generated map.</p></div></li>
          <li><span>03</span><div><b>Hold Ctrl+Space to ask</b><p>Release to hear the answer. Ctrl+Shift+M mutes; Ctrl+Shift+A disables or enables the companion.</p></div></li>
        </ol>
        <div className="download-footnote"><FileArchive size={15} /><span>Windows 10/11 x64 alpha{releaseSize ? ` · ${releaseSize}` : ""}. The model-backed companion expects your private AI layer on this machine; the game itself still runs if that layer is offline.</span></div>
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
          <p>Generate a mission now or download the tested Windows alpha. macOS packaging follows once a real signed artifact is ready.</p>
          <div className="hero-actions">
            <a className="primary-action" href={windowsRelease.url} data-analytics-event="game-download" data-platform="windows-x64"><Download size={17} /> Download Windows alpha</a>
            <a className="text-action" href="#mission-studio">Open mission studio <ArrowRight size={17} /></a>
          </div>
        </div>
      </section>

      <footer>
        <a className="brand" href="#top"><span className="brand-mark">RTS</span><span>RTS <b>AI</b></span></a>
        <p>EA has not endorsed and does not support this product. OpenRA AI is an independent GPL-3.0 project.</p>
        <div><a href={gameSource}>Game source</a><a href={`${gameSource}/blob/main/LICENSE`}>License</a><a href="https://www.openstreetmap.org/copyright">Map attribution</a></div>
      </footer>
    </main>
  );
}
