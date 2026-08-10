export type ConsoleLevel = "log" | "warn" | "error" | "info";
export type ConsoleEntry = { level: ConsoleLevel; message: string; timestamp: string };
export type NetworkEntry = { method: string; url: string; status: number; durationMs: number; timestamp: string };

const consoleEntries: ConsoleEntry[] = [];
const networkEntries: NetworkEntry[] = [];
let initialized = false;

function safeText(value: unknown) {
  try {
    return (typeof value === "string" ? value : JSON.stringify(value)).slice(0, 1_000);
  } catch {
    return String(value).slice(0, 1_000);
  }
}

function safeUrl(input: RequestInfo | URL) {
  try {
    const raw = input instanceof Request ? input.url : String(input);
    const url = new URL(raw, window.location.origin);
    return url.origin === window.location.origin ? url.pathname : `${url.origin}${url.pathname}`;
  } catch {
    return "unknown";
  }
}

export function initDiagnostics() {
  if (initialized || typeof window === "undefined") return;
  initialized = true;

  const levels: ConsoleLevel[] = ["log", "warn", "error", "info"];
  for (const level of levels) {
    const original = console[level].bind(console);
    console[level] = (...args: unknown[]) => {
      consoleEntries.push({ level, message: args.map(safeText).join(" ").slice(0, 2_000), timestamp: new Date().toISOString() });
      if (consoleEntries.length > 100) consoleEntries.splice(0, consoleEntries.length - 100);
      original(...args);
    };
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const started = performance.now();
    const timestamp = new Date().toISOString();
    const method = (init?.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
    try {
      const response = await originalFetch(input, init);
      networkEntries.push({ method, url: safeUrl(input), status: response.status, durationMs: Math.round(performance.now() - started), timestamp });
      if (networkEntries.length > 50) networkEntries.splice(0, networkEntries.length - 50);
      return response;
    } catch (cause) {
      networkEntries.push({ method, url: safeUrl(input), status: 0, durationMs: Math.round(performance.now() - started), timestamp });
      if (networkEntries.length > 50) networkEntries.splice(0, networkEntries.length - 50);
      throw cause;
    }
  };
}

export function getConsoleLogs() {
  return [...consoleEntries];
}

export function getNetworkLogs() {
  return [...networkEntries];
}

export function getBrowserMetadata() {
  if (typeof window === "undefined") return undefined;
  const connection = (navigator as Navigator & { connection?: { effectiveType?: string; downlink?: number; rtt?: number } }).connection;
  return {
    viewport: { width: window.innerWidth, height: window.innerHeight },
    screen: { width: window.screen.width, height: window.screen.height },
    devicePixelRatio: window.devicePixelRatio,
    language: navigator.language,
    platform: navigator.platform,
    cookiesEnabled: navigator.cookieEnabled,
    onLine: navigator.onLine,
    ...(connection ? { connection: { effectiveType: connection.effectiveType, downlink: connection.downlink, rtt: connection.rtt } } : {}),
  };
}
