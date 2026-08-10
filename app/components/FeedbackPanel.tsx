"use client";

import type { User } from "firebase/auth";
import {
  Check,
  CheckCircle2,
  Crosshair,
  MessageSquareText,
  MonitorCog,
  Send,
  Settings2,
  ShieldCheck,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Toaster, toast } from "sonner";
import { feedbackCategories, type FeedbackCapture, type FeedbackCategory } from "../../lib/feedback";
import {
  getBrowserMetadata,
  getConsoleLogs,
  getNetworkLogs,
  initDiagnostics,
} from "../../lib/feedback/diagnostics";
import { useFeedbackStore } from "../../lib/stores/feedback-store";

function describeElement(element: Element) {
  const tag = element.tagName.toLowerCase();
  const id = element.id ? `#${element.id}` : "";
  const classes = [...element.classList].slice(0, 4).map((name) => `.${name}`).join("");
  const label = element.getAttribute("aria-label") || element.getAttribute("title") || element.textContent?.replace(/\s+/g, " ").trim();
  return `${tag}${id}${classes}${label ? ` — “${label.slice(0, 120)}”` : ""}`.slice(0, 500);
}

function selectableAt(x: number, y: number) {
  const element = document.elementFromPoint(x, y);
  if (!element || element === document.documentElement || element === document.body || element.closest("#feedback-widget-root")) return null;
  return element;
}

function ElementSelector({ onSelect, onCancel }: { onSelect: (capture: Omit<FeedbackCapture, "id">) => void; onCancel: () => void }) {
  const [target, setTarget] = useState<{ rect: DOMRect; label: string } | null>(null);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const element = selectableAt(event.clientX, event.clientY);
      setTarget(element ? { rect: element.getBoundingClientRect(), label: describeElement(element) } : null);
    };
    const choose = (event: MouseEvent) => {
      const element = selectableAt(event.clientX, event.clientY);
      if (!element) return;
      event.preventDefault();
      event.stopPropagation();
      onSelect({ elementInfo: describeElement(element), position: { x: Math.round(event.clientX), y: Math.round(event.clientY) } });
    };
    const keydown = (event: KeyboardEvent) => { if (event.key === "Escape") onCancel(); };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("click", choose, true);
    window.addEventListener("keydown", keydown, true);
    return () => {
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("click", choose, true);
      window.removeEventListener("keydown", keydown, true);
    };
  }, [onCancel, onSelect]);

  return (
    <div className="feedback-selector" aria-live="polite">
      <div className="feedback-selector-instruction"><Crosshair size={15} /> Select an element <kbd>Esc</kbd> cancels</div>
      {target && <>
        <div className="feedback-selector-highlight" style={{ left: target.rect.left, top: target.rect.top, width: target.rect.width, height: target.rect.height }} />
        <div className="feedback-selector-tooltip" style={{ left: Math.max(8, Math.min(target.rect.left, window.innerWidth - 330)), top: Math.max(60, target.rect.top - 38) }}>{target.label}</div>
      </>}
    </div>
  );
}

function FeedbackSettings({ onClose }: { onClose: () => void }) {
  const store = useFeedbackStore();
  return (
    <div className="feedback-settings" role="dialog" aria-label="Diagnostic sharing settings">
      <div className="feedback-settings-head"><div><b>Diagnostic context</b><span>Choose exactly what accompanies your note.</span></div><button type="button" onClick={onClose} aria-label="Close diagnostic settings"><X size={16} /></button></div>
      <div className="feedback-settings-toggle"><span><label htmlFor="feedback-metadata">Browser metadata</label><small>Viewport, platform, language, and connection state</small></span><input id="feedback-metadata" type="checkbox" checked={store.includeMetadata} onChange={(event) => store.setSetting("includeMetadata", event.target.checked)} /></div>
      <div className="feedback-settings-toggle"><span><label htmlFor="feedback-console">Console messages</label><small>Recent messages only; disabled by default</small></span><input id="feedback-console" type="checkbox" checked={store.includeConsole} onChange={(event) => store.setSetting("includeConsole", event.target.checked)} /></div>
      {store.includeConsole && <div className="feedback-settings-row"><select aria-label="Console level" value={store.consoleLevel} onChange={(event) => store.setSetting("consoleLevel", event.target.value as "error" | "warn" | "all")}><option value="error">Errors only</option><option value="warn">Warnings + errors</option><option value="all">All messages</option></select><select aria-label="Console message limit" value={store.consoleLimit} onChange={(event) => store.setSetting("consoleLimit", Number(event.target.value))}><option value={10}>Last 10</option><option value={30}>Last 30</option><option value={50}>Last 50</option></select></div>}
      <div className="feedback-settings-toggle"><span><label htmlFor="feedback-network">Network summary</label><small>Method, path, status, and timing—never bodies or headers</small></span><input id="feedback-network" type="checkbox" checked={store.includeNetwork} onChange={(event) => store.setSetting("includeNetwork", event.target.checked)} /></div>
      {store.includeNetwork && <div className="feedback-settings-row"><select aria-label="Network request limit" value={store.networkLimit} onChange={(event) => store.setSetting("networkLimit", Number(event.target.value))}><option value={10}>Last 10 requests</option><option value={20}>Last 20 requests</option><option value={50}>Last 50 requests</option></select></div>}
      <p><ShieldCheck size={13} /> No screenshot, HTML, input value, request body, header, or URL query is collected.</p>
    </div>
  );
}

export function FeedbackPanel({ user, openAuth }: { user: User | null; openAuth: (reason?: string) => void }) {
  const store = useFeedbackStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<{ receipt: string; issueUrl?: string; notificationQueued: boolean } | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [company, setCompany] = useState("");
  const awaitingAuth = useRef(false);
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => initDiagnostics(), []);
  useEffect(() => {
    if (!store.isOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape" && !busy && !settingsOpen) store.close(); };
    window.addEventListener("keydown", closeOnEscape);
    titleRef.current?.focus();
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [store.isOpen, busy, settingsOpen, store]);
  useEffect(() => {
    if (!user || !awaitingAuth.current) return;
    awaitingAuth.current = false;
    store.open();
  }, [user, store]);

  function launch() {
    if (!user) {
      awaitingAuth.current = true;
      openAuth("Sign in to send private feedback");
      return;
    }
    setError("");
    setSuccess(null);
    store.open();
  }

  function beginSelection() {
    setSettingsOpen(false);
    store.setElementSelecting(true);
    toast("Click the part of the page you want to reference. Press Esc to cancel.");
  }

  function selected(capture: Omit<FeedbackCapture, "id">) {
    store.addCapture(capture);
    store.setElementSelecting(false);
    toast.success("Page element attached");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!user || busy || store.title.trim().length < 4 || store.description.trim().length < 10) return;
    setBusy(true);
    setError("");
    try {
      const consoleLogs = getConsoleLogs();
      const filteredConsole = store.consoleLevel === "all"
        ? consoleLogs
        : consoleLogs.filter((entry) => store.consoleLevel === "error" ? entry.level === "error" : entry.level === "warn" || entry.level === "error");
      const token = await user.getIdToken();
      const response = await fetch("/api/feedback", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          title: store.title,
          description: store.description,
          category: store.category,
          rating: store.rating,
          pagePath: window.location.pathname,
          captures: store.captures,
          diagnostics: {
            ...(store.includeMetadata ? { metadata: getBrowserMetadata() } : {}),
            ...(store.includeConsole ? { console: filteredConsole.slice(-store.consoleLimit) } : {}),
            ...(store.includeNetwork ? { network: getNetworkLogs().slice(-store.networkLimit) } : {}),
          },
          clientSubmissionId: crypto.randomUUID(),
          company,
        }),
      });
      const payload = await response.json() as { success?: boolean; receipt?: string; issueUrl?: string; notificationQueued?: boolean; error?: string };
      if (!response.ok || !payload.success || !payload.receipt) throw new Error(payload.error || "Could not save feedback");
      setSuccess({ receipt: payload.receipt, issueUrl: payload.issueUrl, notificationQueued: Boolean(payload.notificationQueued) });
      toast.success("Feedback saved privately");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Could not save feedback. Your message is still here—please try again.";
      setError(message);
      toast.error("Feedback was not sent");
    } finally {
      setBusy(false);
    }
  }

  function close() {
    if (busy) return;
    setSettingsOpen(false);
    setError("");
    if (success) {
      setSuccess(null);
      store.reset();
    } else store.close();
  }

  return (
    <div id="feedback-widget-root">
      <Toaster position="bottom-right" richColors closeButton />
      {!store.hideTrigger && <button type="button" className="feedback-launcher" onClick={launch} aria-haspopup="dialog"><MessageSquareText size={17} /> <span>Feedback</span></button>}
      {store.isElementSelecting && <ElementSelector onSelect={selected} onCancel={() => store.setElementSelecting(false)} />}
      {store.isOpen && (
        <div className="feedback-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}>
          <section className="feedback-dialog" role="dialog" aria-modal="true" aria-labelledby="feedback-title">
            <div className="feedback-dialog-actions">
              {!success && <button type="button" onClick={() => setSettingsOpen((value) => !value)} aria-label="Feedback diagnostic settings" aria-expanded={settingsOpen}><Settings2 size={18} /></button>}
              <button type="button" onClick={close} aria-label="Close feedback"><X size={18} /></button>
            </div>
            {settingsOpen && <FeedbackSettings onClose={() => setSettingsOpen(false)} />}
            {success ? (
              <div className="feedback-success" role="status">
                <span><CheckCircle2 size={28} /></span>
                <p className="eyebrow">Saved privately</p>
                <h2 id="feedback-title">Your feedback is in the builder’s inbox.</h2>
                <p>Receipt <strong>{success.receipt}</strong>. {success.notificationQueued ? "A Firebase mail alert was queued." : "The private issue is saved; its mail alert will be retried separately."}</p>
                <div>{success.issueUrl && <a href={success.issueUrl} target="_blank" rel="noreferrer">Open private issue</a>}<button type="button" onClick={close}>Done</button></div>
              </div>
            ) : (
              <form onSubmit={submit}>
                <div className="feedback-heading">
                  <p className="eyebrow">Private feedback</p>
                  <h2 id="feedback-title">Show us what could be better.</h2>
                  <p>Your note becomes a private issue for the builder. Attach the exact part of the page when context matters.</p>
                </div>
                <div className="feedback-form-grid">
                  <label className="feedback-field"><span>Category</span><select value={store.category} onChange={(event) => store.setCategory(event.target.value as FeedbackCategory)}>{feedbackCategories.map((category) => <option key={category}>{category}</option>)}</select></label>
                  <label className="feedback-field"><span>Short title</span><input ref={titleRef} value={store.title} onChange={(event) => store.setTitle(event.target.value)} minLength={4} maxLength={120} placeholder="What needs attention?" required /></label>
                </div>
                <label className="feedback-field"><span>What happened—or what should we build?</span><textarea value={store.description} onChange={(event) => store.setDescription(event.target.value)} minLength={10} maxLength={4000} placeholder="Include what you expected, what you saw, and why it matters." required /><small>{store.description.length} / 4,000</small></label>
                <div className="feedback-context-bar">
                  <button type="button" onClick={beginSelection}><Crosshair size={16} /> Select page element</button>
                  <span><MonitorCog size={14} /> Page path + {store.includeMetadata ? "browser metadata" : "no browser metadata"}</span>
                </div>
                {store.captures.length > 0 && <div className="feedback-captures" aria-label="Selected page elements">{store.captures.map((capture, index) => <div key={capture.id}><span><Check size={14} /><b>Element {index + 1}</b><small>{capture.elementInfo}</small></span><button type="button" onClick={() => store.removeCapture(capture.id)} aria-label={`Remove element ${index + 1}`}><Trash2 size={15} /></button></div>)}</div>}
                <fieldset className="feedback-rating"><legend>How useful is RTS AI so far? <small>Optional</small></legend><div>{[1, 2, 3, 4, 5].map((value) => <button key={value} type="button" className={store.rating === value ? "is-active" : ""} aria-pressed={store.rating === value} onClick={() => store.setRating(store.rating === value ? null : value)}><Star size={13} fill={store.rating === value ? "currentColor" : "none"} /><b>{value}</b></button>)}</div></fieldset>
                <label className="feedback-honeypot" aria-hidden="true">Company<input tabIndex={-1} autoComplete="off" value={company} onChange={(event) => setCompany(event.target.value)} /></label>
                {error && <p className="feedback-error" role="alert">{error}</p>}
                <div className="feedback-footer"><p><ShieldCheck size={14} /> Signed in as {user?.email || user?.displayName || "a verified user"}. Written feedback and diagnostics are never sent to Google Analytics.</p><button type="submit" disabled={busy || store.title.trim().length < 4 || store.description.trim().length < 10}>{busy ? "Saving…" : <><Send size={15} /> Save privately</>}</button></div>
              </form>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
