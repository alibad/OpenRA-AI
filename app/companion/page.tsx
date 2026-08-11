import type { Metadata } from "next";
import { ArrowRight, BrainCircuit, Map, Mic2, RadioTower, Sparkles } from "lucide-react";
import Link from "next/link";
import { CompanionDemo } from "../components/CompanionDemo";
import { gameSource, SiteFooter, SiteHeader } from "../components/SiteChrome";

export const metadata: Metadata = {
  title: "AI Game Companion | RTS AI",
  description: "Meet the interruptible, fog-respecting AI companion built into OpenRA AI, with voice, safe actions, and optional AUTO command.",
  alternates: { canonical: "/companion" },
};

export default function CompanionPage() {
  return (
    <>
      <SiteHeader />
      <main id="main-content">
        <header className="route-hero route-hero-split">
          <div>
            <span className="eyebrow">AI GAME COMPANION</span>
            <h1>A second mind.<br /><em>Never a second driver.</em></h1>
            <p>It watches the same match you do, speaks only when useful, answers on demand, and gives command back instantly.</p>
            <div className="hero-actions">
              <Link className="primary-action" href="/download">Play with the companion</Link>
              <a className="text-action" href={gameSource} target="_blank" rel="noreferrer">Inspect the game source <ArrowRight size={16} /></a>
            </div>
          </div>
          <CompanionDemo />
        </header>

        <section className="companion-section">
          <div className="section-intro">
            <span className="section-number">HOW IT BEHAVES</span>
            <h2>Helpful enough to speak.<br />Safe enough to act.</h2>
            <p>The companion combines deterministic game state with fog-respecting tactical views. It can explain, propose a safe order for confirmation, or delegate real-time play to OpenRA&apos;s native bot stack when AUTO is explicitly enabled.</p>
          </div>
          <div className="principles">
            <article><RadioTower size={22} /><h3>Notices the change</h3><p>New armor, a power deficit, a lost harvester, or a critically damaged unit—not a running commentary.</p><span>Game event → relevance gate</span></article>
            <article><BrainCircuit size={22} /><h3>Respects fog of war</h3><p>The model receives only the compact observation already visible to you. Hidden enemies stay hidden.</p><span>Snapshot → AI layer → one line</span></article>
            <article><Mic2 size={22} /><h3>You retain command</h3><p>Confirm individual actions, switch strategies by voice, or turn AUTO on. Interrupt speech or disable delegation at any moment.</p><span>Ask · confirm · delegate · take back</span></article>
          </div>
        </section>

        <section className="architecture-section">
          <div className="architecture-copy">
            <span className="section-number">BUILT TO EVOLVE</span>
            <h2>The experience stays stable.<br />The models can change.</h2>
            <p>The game never talks to a model provider directly. A private AI layer owns model credentials and named capabilities, while deterministic OpenRA logic keeps economy, production, combat, and AUTO play moving without waiting on an LLM.</p>
            <a href={gameSource} target="_blank" rel="noreferrer">Read the architecture <ArrowRight size={16} /></a>
          </div>
          <div className="route-diagram" aria-label="AI routing architecture">
            <div><Map size={18} /><span>OpenRA engine<small>fog-respecting snapshot</small></span></div><i />
            <div className="active-route"><Sparkles size={18} /><span>OpenRA AI<small>relevance + safe actions</small></span></div><i />
            <div><RadioTower size={18} /><span>AI layer<small>named model routes</small></span></div><i />
            <div className="model-routes"><span>strategy<small>provider or local model</small></span><span>transcription<small>voice input route</small></span><span>speech<small>spoken response route</small></span></div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
