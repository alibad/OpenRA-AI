"use client";

import { CheckCircle2, LockKeyhole, Mail, ShieldCheck, UserRound, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import {
  createUserWithEmailAndPassword,
  getAdditionalUserInfo,
  GoogleAuthProvider,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
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
  if (code.includes("popup-closed-by-user")) return "Google sign-in was closed before it finished.";
  if (code.includes("popup-blocked")) return "Your browser blocked the Google sign-in window. Allow pop-ups and try again.";
  if (code.includes("account-exists-with-different-credential")) return "That email already uses another sign-in method. Sign in with your password first.";
  if (code.includes("unauthorized-domain") || code.includes("operation-not-allowed")) return "Google sign-in is not enabled for this site yet.";
  return "Sign-in is temporarily unavailable. Please try again.";
}

type BusyAction = "password" | "google" | "reset" | null;

export function AuthDialog({ reason, onClose }: { reason: string; onClose: () => void }) {
  const [mode, setMode] = useState<"signup" | "signin">("signup");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const busy = busyAction !== null;

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
    setBusyAction("password");
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
      setBusyAction(null);
    }
  }

  async function continueWithGoogle() {
    const auth = getFirebaseAuth();
    if (!auth) {
      setError("Account service is not configured on this deployment.");
      return;
    }

    setBusyAction("google");
    setError("");
    setNotice("");
    try {
      const provider = new GoogleAuthProvider();
      provider.setCustomParameters({ prompt: "select_account" });
      const credential = await signInWithPopup(auth, provider);
      const isNewUser = getAdditionalUserInfo(credential)?.isNewUser ?? mode === "signup";
      await trackAnalyticsEvent(isNewUser ? "sign_up" : "login", { method: "google" });
      onClose();
    } catch (cause) {
      setError(friendlyAuthError(cause));
    } finally {
      setBusyAction(null);
    }
  }

  async function resetPassword() {
    const auth = getFirebaseAuth();
    if (!auth || !email.trim()) {
      setError("Enter your email first, then choose reset password.");
      return;
    }
    setBusyAction("reset");
    setError("");
    try {
      await sendPasswordResetEmail(auth, email.trim());
      setNotice("Password reset email sent.");
      void trackAnalyticsEvent("password_reset_requested");
    } catch (cause) {
      setError(friendlyAuthError(cause));
    } finally {
      setBusyAction(null);
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
          <button className="auth-google" type="button" onClick={() => void continueWithGoogle()} disabled={busy || !firebaseIsConfigured}>
            <span className="auth-google-mark" aria-hidden="true">G</span>
            {busyAction === "google" ? "Opening Google…" : mode === "signup" ? "Sign up with Google" : "Sign in with Google"}
          </button>
          <div className="auth-divider" aria-hidden="true"><span>or use email</span></div>
          {mode === "signup" && <label><span><UserRound size={14} /> Your name</span><input autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="How should we address you?" required /></label>}
          <label><span><Mail size={14} /> Email</span><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="commander@example.com" required /></label>
          <label><span><LockKeyhole size={14} /> Password</span><input type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} minLength={6} placeholder="6 characters or more" required /></label>
          {error && <p className="auth-error" role="alert">{error}</p>}
          {notice && <p className="auth-notice" role="status"><CheckCircle2 size={14} /> {notice}</p>}
          <button className="auth-submit" type="submit" disabled={busy || !firebaseIsConfigured}>{busyAction === "password" ? "Securing account…" : mode === "signup" ? "Create account & continue" : "Sign in & continue"}</button>
          {mode === "signin" && <button className="auth-reset" type="button" onClick={() => void resetPassword()} disabled={busy}>Forgot password?</button>}
        </form>

        <div className="auth-privacy"><ShieldCheck size={15} /><p>Your name stays in your Firebase account. Usage analytics is tied to a pseudonymous account ID—never your name, email, mission text, or exact location. <a href="/privacy">Privacy details</a></p></div>
      </section>
    </div>
  );
}
