import { getApp, getApps, initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";
import {
  getAnalytics,
  isSupported,
  logEvent,
  setUserId,
  setUserProperties,
  type Analytics,
} from "firebase/analytics";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID,
};

export const firebaseIsConfigured = Boolean(
  firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId && firebaseConfig.appId,
);

let firebaseApp: FirebaseApp | null = null;
let firebaseAuth: Auth | null = null;
let analyticsPromise: Promise<Analytics | null> | null = null;

function getFirebaseApp() {
  if (!firebaseIsConfigured) return null;
  if (!firebaseApp) firebaseApp = getApps().length ? getApp() : initializeApp(firebaseConfig);
  return firebaseApp;
}

export function getFirebaseAuth() {
  const app = getFirebaseApp();
  if (!app) return null;
  if (!firebaseAuth) firebaseAuth = getAuth(app);
  return firebaseAuth;
}

export function analyticsConsentGranted() {
  return typeof window !== "undefined" && window.localStorage.getItem("rtsai-analytics-consent") === "granted";
}

async function getFirebaseAnalytics() {
  if (!analyticsConsentGranted() || !firebaseConfig.measurementId) return null;
  if (!analyticsPromise) {
    analyticsPromise = (async () => {
      const app = getFirebaseApp();
      if (!app || !(await isSupported())) return null;
      return getAnalytics(app);
    })();
  }
  return analyticsPromise;
}

type AnalyticsParameters = Record<string, string | number | boolean | undefined>;

export async function trackAnalyticsEvent(name: string, parameters: AnalyticsParameters = {}) {
  const analytics = await getFirebaseAnalytics();
  if (!analytics) return;
  const safeParameters = Object.fromEntries(Object.entries(parameters).filter(([, value]) => value !== undefined));
  logEvent(analytics, name, safeParameters);
}

export async function identifyAnalyticsUser(uid: string | null) {
  const analytics = await getFirebaseAnalytics();
  if (!analytics) return;
  setUserId(analytics, uid);
  if (uid) setUserProperties(analytics, { account_type: "registered" });
}

export function resetAnalyticsInitialization() {
  analyticsPromise = null;
}
