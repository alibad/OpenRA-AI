/**
 * Server-only Firebase mail writer.
 *
 * The shared Firebase project already runs the official Trigger Email
 * extension. This writer mints an anonymous Firebase token and writes the
 * extension's strictly bounded document shape through the Firestore REST API.
 * No SMTP credential or service account is exposed to this application.
 */

const mailProjectId = () => process.env.MAIL_FIREBASE_PROJECT_ID ?? "";
const mailApiKey = () => process.env.MAIL_FIREBASE_API_KEY ?? "";

let cachedToken: { idToken: string; expiresAtMs: number } | null = null;

async function anonymousMailToken() {
  if (cachedToken && Date.now() < cachedToken.expiresAtMs - 5 * 60_000) return cachedToken.idToken;
  if (!mailProjectId() || !mailApiKey()) throw new Error("Firebase mail backend is not configured");

  const response = await fetch(
    `https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=${mailApiKey()}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ returnSecureToken: true }),
    },
  );
  if (!response.ok) throw new Error(`Firebase mail authentication failed (${response.status})`);
  const payload = await response.json() as { idToken?: string; expiresIn?: string };
  if (!payload.idToken) throw new Error("Firebase mail authentication returned no token");
  cachedToken = {
    idToken: payload.idToken,
    expiresAtMs: Date.now() + Number(payload.expiresIn ?? 3_600) * 1_000,
  };
  return cachedToken.idToken;
}

type FirestoreValue = Record<string, unknown>;

function encodeValue(value: unknown): FirestoreValue {
  if (value === null || value === undefined) return { nullValue: null };
  if (typeof value === "string") return { stringValue: value };
  if (typeof value === "boolean") return { booleanValue: value };
  if (typeof value === "number")
    return Number.isInteger(value) ? { integerValue: String(value) } : { doubleValue: value };
  if (Array.isArray(value)) return { arrayValue: { values: value.map(encodeValue) } };
  if (typeof value === "object") return { mapValue: { fields: encodeFields(value as Record<string, unknown>) } };
  return { stringValue: String(value) };
}

function encodeFields(value: Record<string, unknown>) {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => item !== undefined).map(([key, item]) => [key, encodeValue(item)]),
  );
}

export function mailGroup() {
  return (process.env.MAIL_GROUP ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

export async function sendFirebaseEmail(input: {
  to: string | string[];
  subject: string;
  html: string;
  text: string;
  cc?: string | string[];
  bcc?: string | string[];
  auditToGroup?: boolean;
}) {
  const token = await anonymousMailToken();
  const to = Array.isArray(input.to) ? input.to : [input.to];
  const bcc = [
    ...(input.bcc ? (Array.isArray(input.bcc) ? input.bcc : [input.bcc]) : []),
    ...(input.auditToGroup === false ? [] : mailGroup()),
  ].filter((value, index, values) => value && !to.includes(value) && values.indexOf(value) === index);
  const document: Record<string, unknown> = {
    to,
    message: {
      subject: input.subject.slice(0, 199),
      html: input.html.slice(0, 32_767),
      text: input.text.slice(0, 32_767),
    },
  };
  if (input.cc) document.cc = Array.isArray(input.cc) ? input.cc : [input.cc];
  if (bcc.length) document.bcc = bcc;

  const response = await fetch(
    `https://firestore.googleapis.com/v1/projects/${mailProjectId()}/databases/(default)/documents/mail`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ fields: encodeFields(document) }),
    },
  );
  if (!response.ok) {
    const detail = (await response.text()).replace(/[A-Za-z0-9_-]{32,}/g, "[redacted]").slice(0, 500);
    throw new Error(`Firebase mail write failed (${response.status}): ${detail}`);
  }
  const result = await response.json() as { name?: string };
  return result.name?.split("/").pop() ?? null;
}
