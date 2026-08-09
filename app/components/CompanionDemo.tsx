"use client";

import { AudioLines, Mic2, Pause, Play, Radio, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";

const situations = [
  {
    label: "THREAT / HIGH",
    line: "Heavy armor is entering from the east. Your northern route is still open.",
    power: "130 / 90",
    contacts: "2 NEW",
    sector: "EAST 48,20",
  },
  {
    label: "ECONOMY / WATCH",
    line: "Your only harvester is exposed. The southern ore field is the safer rotation.",
    power: "110 / 90",
    contacts: "1 TRACKED",
    sector: "SOUTH 31,54",
  },
  {
    label: "BASE / CRITICAL",
    line: "Power is about to fail. Pause vehicle production or place another generator now.",
    power: "70 / 120",
    contacts: "0 VISIBLE",
    sector: "HOME 14,18",
  },
] as const;

export function CompanionDemo() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [listening, setListening] = useState(false);
  const situation = situations[index];

  useEffect(() => {
    if (paused || listening) return;
    const timer = window.setInterval(() => setIndex((current) => (current + 1) % situations.length), 5600);
    return () => window.clearInterval(timer);
  }, [listening, paused]);

  function ask() {
    setListening(true);
    window.setTimeout(() => {
      setIndex((current) => (current + 1) % situations.length);
      setListening(false);
    }, 1350);
  }

  return (
    <div className="companion-demo" aria-label="Interactive AI companion preview">
      <div className="demo-topline">
        <span>COMPANION / LIVE</span>
        <span className="demo-route"><Radio size={12} /> OBSERVATION ONLY</span>
      </div>
      <div className="battle-state">
        <div className="mini-map" aria-hidden="true">
          <span className="unit friendly a" /><span className="unit friendly b" />
          <span className="unit hostile c" /><span className="unit hostile d" />
          <i className="sweep" />
        </div>
        <div className="state-readout">
          <span>POWER<b className={index === 2 ? "hostile-text" : ""}>{situation.power}</b></span>
          <span>CONTACTS<b className="hostile-text">{situation.contacts}</b></span>
          <span>SECTOR<b>{situation.sector}</b></span>
        </div>
      </div>
      <div className="spoken-line" aria-live="polite">
        {listening ? <Volume2 className="pulse" size={20} /> : <AudioLines size={20} />}
        <div>
          <span>{listening ? "LISTENING / RELEASE TO ASK" : situation.label}</span>
          <p>{listening ? "Listening for your question…" : `“${situation.line}”`}</p>
        </div>
      </div>
      <div className="demo-controls">
        <button type="button" onClick={() => setPaused((value) => !value)} aria-pressed={paused}>
          {paused ? <Play size={14} /> : <Pause size={14} />} {paused ? "Resume" : "Pause"}
        </button>
        <button type="button" onClick={ask} disabled={listening}><Mic2 size={14} /> Ask</button>
        <div className="scenario-dots" aria-label={`Scenario ${index + 1} of ${situations.length}`}>
          {situations.map((_, scenarioIndex) => <i key={scenarioIndex} className={scenarioIndex === index ? "active" : ""} />)}
        </div>
        <span>1.4s</span>
      </div>
    </div>
  );
}
