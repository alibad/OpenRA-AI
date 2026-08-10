"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { onAuthStateChanged, signOut, type User } from "firebase/auth";
import {
  getFirebaseAuth,
  firebaseIsConfigured,
  identifyAnalyticsUser,
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
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
