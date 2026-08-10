"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { onAuthStateChanged, signOut, type User } from "firebase/auth";
import {
  getFirebaseAuth,
  firebaseIsConfigured,
  identifyAnalyticsUser,
  resetAnalyticsInitialization,
  trackAnalyticsEvent,
} from "../../lib/firebase-client";
import { AuthDialog } from "./AuthDialog";

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  openAuth: (reason?: string) => void;
  closeAuth: () => void;
  signOutUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function AnalyticsConsent() {
  const choice = useSyncExternalStore(
    (notify) => {
      window.addEventListener("rtsai:analytics-consent", notify);
      return () => window.removeEventListener("rtsai:analytics-consent", notify);
    },
    () => window.localStorage.getItem("rtsai-analytics-consent") ?? "unknown",
    () => "unknown",
  );

  function choose(next: "granted" | "denied") {
    window.localStorage.setItem("rtsai-analytics-consent", next);
    resetAnalyticsInitialization();
    window.dispatchEvent(new CustomEvent("rtsai:analytics-consent"));
    if (next === "granted") void trackAnalyticsEvent("analytics_consent", { status: "granted" });
  }

  if (choice !== "unknown") return null;
  return (
    <aside className="consent-banner" aria-label="Analytics preference">
      <div>
        <strong>Help improve RTS AI</strong>
        <p>Optional Google Analytics measures feature use with a pseudonymous account ID. We never send your name, email, mission text, or exact map coordinates.</p>
      </div>
      <div className="consent-actions">
        <button type="button" className="consent-decline" onClick={() => choose("denied")}>Not now</button>
        <button type="button" className="consent-accept" onClick={() => choose("granted")}>Allow analytics</button>
      </div>
    </aside>
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(firebaseIsConfigured);
  const [authReason, setAuthReason] = useState<string | null>(null);

  useEffect(() => {
    const auth = getFirebaseAuth();
    if (!auth) return;
    return onAuthStateChanged(auth, (nextUser) => {
      setUser(nextUser);
      setLoading(false);
      void identifyAnalyticsUser(nextUser?.uid ?? null);
    });
  }, []);

  useEffect(() => {
    const syncIdentity = () => void identifyAnalyticsUser(user?.uid ?? null);
    window.addEventListener("rtsai:analytics-consent", syncIdentity);
    return () => window.removeEventListener("rtsai:analytics-consent", syncIdentity);
  }, [user]);

  useEffect(() => {
    const trackAttributedClick = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest<HTMLElement>("[data-analytics-event]") : null;
      if (!target) return;
      void trackAnalyticsEvent(target.dataset.analyticsEvent ?? "link_click", {
        platform: target.dataset.platform,
        surface: target.dataset.analyticsSurface,
      });
    };
    document.addEventListener("click", trackAttributedClick);
    return () => document.removeEventListener("click", trackAttributedClick);
  }, []);

  const openAuth = useCallback((reason = "Sign in to use RTS AI") => setAuthReason(reason), []);
  const closeAuth = useCallback(() => setAuthReason(null), []);
  const signOutUser = useCallback(async () => {
    const auth = getFirebaseAuth();
    if (!auth) return;
    await signOut(auth);
    await trackAnalyticsEvent("logout");
  }, []);

  const value = useMemo(() => ({ user, loading, openAuth, closeAuth, signOutUser }), [user, loading, openAuth, closeAuth, signOutUser]);

  return (
    <AuthContext.Provider value={value}>
      {children}
      {authReason && <AuthDialog reason={authReason} onClose={closeAuth} />}
      <AnalyticsConsent />
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
