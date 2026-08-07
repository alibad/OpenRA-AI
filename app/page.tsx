import {
  ArrowRight,
  AudioLines,
  BrainCircuit,
  Github,
  Map,
  Mic2,
  Pause,
  RadioTower,
  ShieldCheck,
  Sparkles,
  VolumeX,
  Zap,
} from "lucide-react";
import { MissionStudio } from "./components/MissionStudio";

const github = "https://github.com/alibad/OpenRA-AI";

export default function Home() {
  return (
    <main>
      <nav className="site-nav" aria-label="Primary navigation">
        <a className="brand" href="#top" aria-label="OpenRA AI home">
          <span className="brand-mark">OA</span>
          <span>OPENRA <b>AI</b></span>
        </a>
        <div className="nav-links">
          <a href="#companion">Companion</a>
          <a href="#mission-studio">Mission studio</a>
          <a href="#architecture">How it works</a>
        </div>
        <a className="nav-source" href={github} target="_blank" rel="noreferrer"><Github size={15} /> Source</a>
      </nav>

      <header className="hero" id="top">
        <div className="hero-radar" aria-hidden="true"><i /><i /><i /><span /></div>
        <div className="hero-copy">
          <span className="eyebrow"><span className="live-dot" /> Open source / playable alpha</span>
          <h1>Your battlefield.<br /><em>Now it talks back.</em></h1>
          <p className="hero-lede">A quiet AI companion for OpenRA—and a map generator that turns any place on Earth into a fictional, playable skirmish.</p>
          <div className="hero-actions">
            <a className="primary-action" href="#mission-studio">Build a mission <ArrowRight size={17} /></a>
            <a className="text-action" href={github} target="_blank" rel="noreferrer"><Github size={17} /> Explore the code</a>
          </div>
          <div className="hero-proof">
            <span><ShieldCheck size={15} /> Observation-only</span>
            <span><VolumeX size={15} /> Interruptible</span>
            <span><Zap size={15} /> BeTenshi-routed</span>
          </div>
        </div>
        <div className="companion-demo" aria-label="Example AI companion exchange">
          <div className="demo-topline"><span>COMPANION / LIVE</span><span className="signal-bars"><i /><i /><i /></span></div>
          <div className="battle-state">
            <div className="mini-map" aria-hidden="true">
              <span className="unit friendly a" /><span className="unit friendly b" />
              <span className="unit hostile c" /><span className="unit hostile d" />
              <i className="sweep" />
            </div>
            <div className="state-readout">
              <span>POWER<b>130 / 90</b></span>
              <span>CONTACTS<b className="hostile-text">2 NEW</b></span>
              <span>SECTOR<b>EAST 48,20</b></span>
            </div>
          </div>
          <div className="spoken-line">
            <AudioLines size={20} />
            <p>“Heavy armor is entering from the east. Your northern route is still open.”</p>
          </div>
          <div className="demo-controls"><button><Pause size={14} /> Stop</button><button><Mic2 size={14} /> Ask</button><span>1.4s</span></div>
        </div>
      </header>

      <div className="capability-rail" aria-label="Core capabilities">
        <span>01 <b>Notices what matters</b></span>
        <span>02 <b>Answers about this match</b></span>
        <span>03 <b>Turns Earth into terrain</b></span>
        <span>04 <b>Ships ordinary .oramap files</b></span>
      </div>

      <section className="companion-section" id="companion">
        <div className="section-intro">
          <span className="section-number">01 / COMPANION</span>
          <h2>Helpful enough to speak.<br />Quiet enough to keep.</h2>
          <p>OpenRA AI watches structured game state—not a constant video feed. Deterministic rules decide whether something is worth your attention before a model is called.</p>
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
            <span>Snapshot → BeTenshi → one line</span>
          </article>
          <article>
            <Mic2 size={22} />
            <h3>Yields instantly</h3>
            <p>Ask by voice, cut it off, mute it, or disable it. No modal panels and no AI-issued game orders.</p>
            <span>Speak · interrupt · continue playing</span>
          </article>
        </div>
      </section>

      <MissionStudio />

      <section className="architecture-section" id="architecture">
        <div className="architecture-copy">
          <span className="section-number">03 / BUILT TO EVOLVE</span>
          <h2>The experience stays stable.<br />The models can change.</h2>
          <p>The game never talks to a provider directly. BeTenshi owns model credentials and named capabilities, so cloud models can be replaced by local ones later without rewriting the OpenRA integration.</p>
          <a href={github} target="_blank" rel="noreferrer">Read the architecture <ArrowRight size={16} /></a>
        </div>
        <div className="route-diagram" aria-label="AI routing architecture">
          <div><Map size={18} /><span>OpenRA engine<small>fog-respecting snapshot</small></span></div>
          <i />
          <div className="active-route"><Sparkles size={18} /><span>OpenRA AI<small>relevance + interruption</small></span></div>
          <i />
          <div><RadioTower size={18} /><span>BeTenshi<small>named model routes</small></span></div>
          <i />
          <div className="model-routes">
            <span>gpt-5.5<small>battlefield language</small></span>
            <span>transcribe<small>voice input</small></span>
            <span>tts<small>spoken response</small></span>
          </div>
        </div>
      </section>

      <section className="closing-section">
        <div>
          <span className="eyebrow">Built in the open</span>
          <h2>Pick a place.<br />Start a story.</h2>
        </div>
        <div>
          <p>Generate a mission now, or build the companion and engine locally on Windows. macOS packaging follows once signing infrastructure is ready.</p>
          <div className="hero-actions">
            <a className="primary-action" href="#mission-studio">Open mission studio <ArrowRight size={17} /></a>
            <a className="text-action" href={`${github}#development`} target="_blank" rel="noreferrer">Local setup</a>
          </div>
        </div>
      </section>

      <footer>
        <a className="brand" href="#top"><span className="brand-mark">OA</span><span>OPENRA <b>AI</b></span></a>
        <p>Independent GPL-3.0 project. Not affiliated with OpenRA or Electronic Arts.</p>
        <div><a href={github}>GitHub</a><a href={`${github}/blob/main/LICENSE`}>License</a><a href="https://www.openstreetmap.org/copyright">Map attribution</a></div>
      </footer>
    </main>
  );
}
