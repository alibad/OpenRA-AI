import type { Metadata } from "next";
import { Apple, BrainCircuit, CalendarDays, CheckCircle2, Download, FileArchive, MonitorDown, Sparkles } from "lucide-react";
import Link from "next/link";
import { SiteFooter, SiteHeader } from "../components/SiteChrome";
import { currentShowcase } from "../../lib/product-plan";
import { getGameRelease } from "../../lib/release";

export const metadata: Metadata = {
  title: "Download OpenRA AI | RTS AI",
  description: "Download the verified OpenRA AI game for Windows, check macOS availability, and optionally install the private local AI model pack.",
  alternates: { canonical: "/download" },
};

function formatBytes(bytes: number | null) {
  if (!bytes) return null;
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string | null) {
  if (!value) return "Verified release";
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

export default async function DownloadPage() {
  const gameRelease = await getGameRelease();
  const windowsRelease = gameRelease.windows;
  const primaryWindowsUrl = windowsRelease.installerUrl ?? windowsRelease.url;
  const primaryWindowsSize = formatBytes(windowsRelease.installerSizeBytes ?? windowsRelease.sizeBytes);
  const aiPackSize = formatBytes(windowsRelease.aiPackSizeBytes);
  const appleSiliconRelease = gameRelease.macos?.assets.find((asset) => asset.architecture === "arm64");
  const intelMacRelease = gameRelease.macos?.assets.find((asset) => asset.architecture === "x64");

  return (
    <>
      <SiteHeader />
      <main id="main-content">
        <header className="route-hero download-route-hero">
          <span className="eyebrow">PLAYABLE BUILD / {windowsRelease.version}</span>
          <h1>Install. Launch.<br /><em>Command.</em></h1>
          <p>The current release includes the engine, companion, AUTO strategy layer, Earth tools, and the latest playable vertical slice.</p>
          <div className="release-trust" aria-label="Release details">
            <span><CheckCircle2 size={15} /> Locally built and smoke-tested</span>
            <span><CalendarDays size={15} /> Released {formatDate(windowsRelease.publishedAt)}</span>
            <Link href={`/platform#${currentShowcase.slug}`}><Sparkles size={15} /> Current playable proof</Link>
          </div>
        </header>

        <section className="download-section download-route-section" aria-labelledby="download-title">
          <div className="download-intro">
            <span className="section-number">CHOOSE YOUR PLATFORM</span>
            <h2 id="download-title">The game first.<br />Models optional.</h2>
            <p>OpenRA AI remains playable when the model layer is offline. Add cloud routes or the local AI pack when you want companion vision, transcription, and speech.</p>
          </div>
          <div className="platform-downloads" aria-label="Platform downloads">
            <article className="platform-card is-ready">
              <div className="platform-card-heading"><span className="platform-icon"><MonitorDown size={23} /></span><div><span className="platform-kicker">Windows 10 / 11</span><h3>Windows x64</h3></div><span className="release-status is-ready">Ready</span></div>
              <p>A normal per-user setup with the RTS AI app icon, Start menu entry, desktop shortcut, uninstaller, and included scenario launchers.</p>
              <a className="primary-action platform-primary" href={primaryWindowsUrl} data-analytics-event="game-download" data-platform="windows-x64-setup"><Download size={17} /> Download Windows setup</a>
              <div className="platform-meta"><span>{primaryWindowsSize ?? "Setup executable"}</span>{windowsRelease.installerChecksumUrl && <a href={windowsRelease.installerChecksumUrl}>Setup checksum</a>}<a href={windowsRelease.url} data-analytics-event="game-download" data-platform="windows-x64-portable">Portable ZIP</a><a href={windowsRelease.checksumUrl}>ZIP checksum</a></div>
            </article>

            <article className={`platform-card ${gameRelease.macos ? "is-ready" : "is-pending"}`}>
              <div className="platform-card-heading"><span className="platform-icon"><Apple size={23} /></span><div><span className="platform-kicker">Apple desktop</span><h3>macOS</h3></div><span className={`release-status ${gameRelease.macos ? "is-ready" : "is-pending"}`}>{gameRelease.macos ? "Ready" : "Signing"}</span></div>
              {gameRelease.macos ? <><p>A native signed disk image. Choose the build that matches your Mac.</p><div className="mac-download-actions">{appleSiliconRelease && <a className="primary-action platform-primary" href={appleSiliconRelease.url} data-analytics-event="game-download" data-platform="macos-arm64"><Download size={17} /> Apple silicon</a>}{intelMacRelease && <a className="secondary-download" href={intelMacRelease.url} data-analytics-event="game-download" data-platform="macos-x64">Intel Mac</a>}</div><div className="platform-meta"><span>Version {gameRelease.macos.version}</span>{appleSiliconRelease?.checksumUrl && <a href={appleSiliconRelease.checksumUrl}>Apple silicon checksum</a>}{intelMacRelease?.checksumUrl && <a href={intelMacRelease.checksumUrl}>Intel checksum</a>}</div></> : <><p>The native app and DMG packaging path is complete. Its public download stays locked until the artifact is built, signed, and notarized on a Mac.</p><span className="pending-download" aria-disabled="true">Signed macOS download pending</span><div className="platform-meta"><span>Apple silicon + Intel pipeline</span><span>No placeholder download</span></div></>}
            </article>
          </div>

          {windowsRelease.aiPackUrl && <div className="ai-pack-callout"><span className="platform-icon"><BrainCircuit size={22} /></span><div><b>Optional Local AI Pack</b><p>Qwen3-VL, Whisper, and Kokoro—the pinned model payload for private local vision, transcription, and speech.</p></div><span>{aiPackSize ?? "Model bundle"}</span><a href={windowsRelease.aiPackUrl} data-analytics-event="ai-pack-download" data-platform="windows-x64"><Download size={15} /> Download AI Pack</a>{windowsRelease.aiPackChecksumUrl && <a className="checksum-link" href={windowsRelease.aiPackChecksumUrl}>Checksum</a>}</div>}

          <ol className="play-steps">
            <li><span>01</span><div><b>Install or extract</b><p>Use Windows setup for shortcuts and uninstall support, or keep the ZIP fully portable.</p></div></li>
            <li><span>02</span><div><b>Choose your battlefield</b><p>Launch OpenRA AI normally, or run <code>{currentShowcase.launcher}</code> to open the current authored vertical slice.</p></div></li>
            <li><span>03</span><div><b>Hold Ctrl+Space to ask</b><p>Release to hear the answer. Ctrl+Shift+M mutes; Ctrl+Shift+A disables or enables the companion.</p></div></li>
          </ol>
          <div className="download-footnote"><FileArchive size={15} /><span>Checksums are published beside every downloadable artifact. The model-backed companion expects your private AI layer on this machine; the game itself still runs if that layer is offline.</span></div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
