"use client";

import { CheckCircle2, LockKeyhole, Mail, ShieldCheck, UserRound, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import {
  createUserWithEmailAndPassword,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  updateProfile,
} from "firebase/auth";
import { firebaseIsConfigured, getFirebaseAuth, trackAnalyticsEvent } from "../../lib/firebase-client";

function friendlyAuthError(cause: unknown) {
  const code = typeof cause === "object" && cause && "code" in cause ? String(cause.code) : "";
  if (code.includes("email-already-in-use")) return "That email already has an account. Sign in instead.";
  if (code.includes("invalid-credential")) return "The email or password does not match.";
  if (code.includes("weak-password")) return "Use at least six characters for your password.";
  if (code.includes("invalid-email")) return "Enter a valid email address.";
  if (code.includes("too-many-requests")) return "Too many attempts. Wait a moment and try again.";
  return "Sign-in is temporarily unavailable. Please try again.";
}

export function AuthDialog({ reason, onClose }: { reason: string; onClose: () => void }) {
  const [mode, setMode] = useState<"signup" | "signin">("signup");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const auth = getFirebaseAuth();
    if (!auth) {
      setError("Account service is not configured on this deployment.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "signup") {
        const credential = await createUserWithEmailAndPassword(auth, email.trim(), password);
        const displayName = name.trim();
        if (displayName) await updateProfile(credential.user, { displayName });
        void sendEmailVerification(credential.user).catch(() => undefined);
        await trackAnalyticsEvent("sign_up", { method: "password" });
      } else {
        await signInWithEmailAndPassword(auth, email.trim(), password);
        await trackAnalyticsEvent("login", { method: "password" });
      }
      onClose();
    } catch (cause) {
      setError(friendlyAuthError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword() {
    const auth = getFirebaseAuth();
    if (!auth || !email.trim()) {
      setError("Enter your email first, then choose reset password.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await sendPasswordResetEmail(auth, email.trim());
      setNotice("Password reset email sent.");
      void trackAnalyticsEvent("password_reset_requested");
    } catch (cause) {
      setError(friendlyAuthError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title">
        <button type="button" className="auth-close" onClick={onClose} aria-label="Close account dialog"><X size={18} /></button>
        <div className="auth-intro">
          <span className="auth-emblem"><LockKeyhole size={23} /></span>
          <span className="eyebrow">Commander account</span>
          <h2 id="auth-title">{mode === "signup" ? "Create your free profile." : "Welcome back, Commander."}</h2>
          <p>{reason}. Explore and download publicly; an account is required only when you ask RTS AI to do work for you.</p>
        </div>

        <div className="auth-tabs" role="tablist" aria-label="Account action">
          <button type="button" role="tab" aria-selected={mode === "signup"} onClick={() => { setMode("signup"); setError(""); }}>Create account</button>
          <button type="button" role="tab" aria-selected={mode === "signin"} onClick={() => { setMode("signin"); setError(""); }}>Sign in</button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          {mode === "signup" && <label><span><UserRound size={14} /> Your name</span><input autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="How should we address you?" required /></label>}
          <label><span><Mail size={14} /> Email</span><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="commander@example.com" required /></label>
          <label><span><LockKeyhole size={14} /> Password</span><input type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} minLength={6} placeholder="6 characters or more" required /></label>
          {error && <p className="auth-error" role="alert">{error}</p>}
          {notice && <p className="auth-notice" role="status"><CheckCircle2 size={14} /> {notice}</p>}
          <button className="auth-submit" type="submit" disabled={busy || !firebaseIsConfigured}>{busy ? "Securing account…" : mode === "signup" ? "Create account & continue" : "Sign in & continue"}</button>
          {mode === "signin" && <button className="auth-reset" type="button" onClick={() => void resetPassword()} disabled={busy}>Forgot password?</button>}
        </form>

        <div className="auth-privacy"><ShieldCheck size={15} /><p>Your name stays in your Firebase account. Usage analytics is tied to a pseudonymous account ID—never your name, email, mission text, or exact location. <a href="/privacy">Privacy details</a></p></div>
      </section>
    </div>
  );
}
