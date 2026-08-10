"use client";

import { CheckCircle2, MessageSquareText, Send, ShieldCheck, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import type { User } from "firebase/auth";
import { feedbackCategories, type FeedbackCategory } from "../../lib/feedback";
import { trackAnalyticsEvent } from "../../lib/firebase-client";

const labels: Record<FeedbackCategory, string> = {
  idea: "Idea",
  bug: "Bug",
  gameplay: "Gameplay",
  "mission-generator": "Mission generator",
  "ai-companion": "AI companion",
  website: "Website",
  other: "Other",
};

export function FeedbackPanel({ user, openAuth }: { user: User | null; openAuth: (reason?: string) => void }) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<FeedbackCategory>("idea");
  const [rating, setRating] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [includePage, setIncludePage] = useState(true);
  const [company, setCompany] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState("");
  const [awaitingAuth, setAwaitingAuth] = useState(false);
  const messageRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape" && !busy) setOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    messageRef.current?.focus();
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, busy]);

  useEffect(() => {
    if (!user || !awaitingAuth) return;
    setAwaitingAuth(false);
    setOpen(true);
    setError("");
    void trackAnalyticsEvent("feedback_opened", { after_auth: true });
  }, [user, awaitingAuth]);

  function launch() {
    if (!user) {
      setAwaitingAuth(true);
      openAuth("Sign in to send private feedback");
      void trackAnalyticsEvent("feedback_auth_required");
      return;
    }
    setOpen(true);
    setError("");
    void trackAnalyticsEvent("feedback_opened");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!user || message.trim().length < 10 || busy) return;
    setBusy(true);
    setError("");
    const clientSubmissionId = crypto.randomUUID();
    try {
      const token = await user.getIdToken();
      const response = await fetch("/api/feedback", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          category,
          rating,
          message,
          pagePath: includePage ? window.location.pathname : null,
          clientSubmissionId,
          company,
        }),
      });
      const payload = await response.json() as { ok?: boolean; id?: string; error?: string };
      if (!response.ok || !payload.ok || !payload.id) throw new Error(payload.error || "Could not send feedback");
      setReceipt(payload.id);
      await trackAnalyticsEvent("feedback_submitted", { category, rating: rating ?? 0 });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not send feedback. Your message is still here—please try again.");
    } finally {
      setBusy(false);
    }
  }

  function close() {
    if (busy) return;
    setOpen(false);
    if (receipt) {
      setMessage("");
      setRating(null);
      setReceipt("");
    }
  }

  return (
    <>
      <button type="button" className="feedback-launcher" onClick={launch} aria-haspopup="dialog">
        <MessageSquareText size={17} /> <span>Feedback</span>
      </button>
      {open && (
        <div className="feedback-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}>
          <section className="feedback-dialog" role="dialog" aria-modal="true" aria-labelledby="feedback-title">
            <button type="button" className="feedback-close" onClick={close} aria-label="Close feedback"><X size={18} /></button>
            {receipt ? (
              <div className="feedback-success" role="status">
                <span><CheckCircle2 size={28} /></span>
                <p className="eyebrow">Received privately</p>
                <h2 id="feedback-title">Thank you. This goes straight to the builder.</h2>
                <p>Your receipt is <strong>{receipt}</strong>. The message is not sent to Google Analytics.</p>
                <button type="button" onClick={close}>Done</button>
              </div>
            ) : (
              <form onSubmit={submit}>
                <div className="feedback-heading">
                  <p className="eyebrow">Direct line</p>
                  <h2 id="feedback-title">Make RTS AI better.</h2>
                  <p>Report friction, share an idea, or tell us what felt magical. Your signed-in account lets us reply.</p>
                </div>

                <label className="feedback-field"><span>What is this about?</span><select value={category} onChange={(event) => setCategory(event.target.value as FeedbackCategory)}>{feedbackCategories.map((value) => <option key={value} value={value}>{labels[value]}</option>)}</select></label>

                <fieldset className="feedback-rating"><legend>How useful is RTS AI so far? <small>Optional</small></legend><div>{[1, 2, 3, 4, 5].map((value) => <button key={value} type="button" className={rating === value ? "is-active" : ""} aria-pressed={rating === value} onClick={() => setRating(rating === value ? null : value)}><b>{value}</b><span>{value === 1 ? "Rough" : value === 5 ? "Excellent" : ""}</span></button>)}</div></fieldset>

                <label className="feedback-field"><span>Your feedback</span><textarea ref={messageRef} value={message} onChange={(event) => setMessage(event.target.value)} minLength={10} maxLength={2000} placeholder="What happened, what did you expect, or what should we build next?" required /><small>{message.length} / 2,000</small></label>
                <label className="feedback-context"><input type="checkbox" checked={includePage} onChange={(event) => setIncludePage(event.target.checked)} /><span>Include this page path for context</span></label>
                <label className="feedback-honeypot" aria-hidden="true">Company<input tabIndex={-1} autoComplete="off" value={company} onChange={(event) => setCompany(event.target.value)} /></label>
                {error && <p className="feedback-error" role="alert">{error}</p>}
                <div className="feedback-footer"><p><ShieldCheck size={14} /> Private message. Analytics receives only category and rating.</p><button type="submit" disabled={busy || message.trim().length < 10}>{busy ? "Sending…" : <><Send size={15} /> Send feedback</>}</button></div>
              </form>
            )}
          </section>
        </div>
      )}
    </>
  );
}
