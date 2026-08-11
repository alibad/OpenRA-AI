import { ArrowRight, CheckCircle2, Download } from "lucide-react";
import Image from "next/image";
import { currentShowcase } from "../../lib/product-plan";
import { gameSource } from "./SiteChrome";

export function CurrentShowcase({ downloadUrl, version, compact = false }: { downloadUrl: string; version: string; compact?: boolean }) {
  return (
    <article className={`current-showcase${compact ? " current-showcase-compact" : ""}`} id={currentShowcase.slug}>
      <div className="showcase-visual">
        <Image src={currentShowcase.image} alt="Current OpenRA AI vertical-slice key art showing a coastal battlefield" fill sizes="(max-width: 1050px) 100vw, 55vw" />
        <span className="showcase-release-tag"><i /> {currentShowcase.label} · {version}</span>
        <div className="showcase-readout"><span>FIRST CONTRACT</span><b>{currentShowcase.mission}</b><small>Earth-derived · validated · playable</small></div>
      </div>
      <div className="showcase-copy">
        <span className="section-number">PLAYABLE NOW</span>
        <h3>{currentShowcase.title}</h3>
        <p>{currentShowcase.description}</p>
        {!compact && <ul>{currentShowcase.highlights.map((highlight) => <li key={highlight}><CheckCircle2 size={14} /> {highlight}</li>)}</ul>}
        <div className="showcase-actions">
          <a className="primary-action" href={downloadUrl} data-analytics-event="game-download" data-platform="current-showcase"><Download size={17} /> Play current build</a>
          <a className="text-action" href={`${gameSource}${currentShowcase.docsPath}`} target="_blank" rel="noreferrer">See the vertical slice <ArrowRight size={16} /></a>
        </div>
      </div>
    </article>
  );
}
