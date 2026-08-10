import { importPKCS8, SignJWT } from "jose";

export const GITHUB_OWNER = process.env.GITHUB_REPO_OWNER || "alibad";
export const GITHUB_REPO = process.env.GITHUB_REPO_NAME || "RTSAI-Web";

let cachedInstallationToken: { token: string; expiresAtMs: number } | null = null;

function derLength(length: number) {
  if (length < 128) return new Uint8Array([length]);
  const bytes: number[] = [];
  for (let value = length; value > 0; value >>= 8) bytes.unshift(value & 0xff);
  return new Uint8Array([0x80 | bytes.length, ...bytes]);
}

function concatenate(...arrays: Uint8Array[]) {
  const output = new Uint8Array(arrays.reduce((total, item) => total + item.length, 0));
  let offset = 0;
  for (const item of arrays) { output.set(item, offset); offset += item.length; }
  return output;
}

function pkcs1ToPkcs8(pem: string) {
  const body = pem.replace(/-----[^-]+-----|\s/g, "");
  const binary = atob(body);
  const pkcs1 = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  const version = new Uint8Array([0x02, 0x01, 0x00]);
  const rsaAlgorithm = new Uint8Array([0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01, 0x05, 0x00]);
  const octetString = concatenate(new Uint8Array([0x04]), derLength(pkcs1.length), pkcs1);
  const content = concatenate(version, rsaAlgorithm, octetString);
  const pkcs8 = concatenate(new Uint8Array([0x30]), derLength(content.length), content);
  let encoded = "";
  for (let offset = 0; offset < pkcs8.length; offset += 8_190)
    encoded += btoa(String.fromCharCode(...pkcs8.subarray(offset, offset + 8_190)));
  return `-----BEGIN PRIVATE KEY-----\n${encoded.match(/.{1,64}/g)?.join("\n")}\n-----END PRIVATE KEY-----`;
}

function privateKey() {
  const raw = process.env.GITHUB_APP_PRIVATE_KEY || "";
  let decoded = raw.startsWith("-----") ? raw.replace(/\\n/g, "\n") : raw;
  try {
    if (!decoded.startsWith("-----")) decoded = atob(raw);
  } catch {
    decoded = raw;
  }
  return decoded.includes("BEGIN RSA PRIVATE KEY") ? pkcs1ToPkcs8(decoded) : decoded;
}

export function isGitHubConfigured() {
  return Boolean(
    process.env.GITHUB_APP_ID &&
    process.env.GITHUB_APP_INSTALLATION_ID &&
    process.env.GITHUB_APP_PRIVATE_KEY,
  );
}

async function appJwt() {
  if (!process.env.GITHUB_APP_ID) throw new Error("GitHub App is not configured");
  const key = await importPKCS8(privateKey(), "RS256");
  const now = Math.floor(Date.now() / 1_000);
  return new SignJWT({})
    .setProtectedHeader({ alg: "RS256" })
    .setIssuedAt(now - 60)
    .setIssuer(process.env.GITHUB_APP_ID)
    .setExpirationTime(now + 540)
    .sign(key);
}

export class GitHubRequestError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "GitHubRequestError";
  }
}

async function installationToken() {
  if (cachedInstallationToken && Date.now() < cachedInstallationToken.expiresAtMs - 5 * 60_000)
    return cachedInstallationToken.token;
  if (!isGitHubConfigured()) throw new Error("GitHub App is not configured");
  const response = await fetch(
    `https://api.github.com/app/installations/${process.env.GITHUB_APP_INSTALLATION_ID}/access_tokens`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${await appJwt()}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "rtsai-feedback",
      },
    },
  );
  const payload = await response.json() as { token?: string; expires_at?: string; message?: string };
  if (!response.ok || !payload.token)
    throw new GitHubRequestError(response.status, payload.message || "GitHub installation authentication failed");
  cachedInstallationToken = {
    token: payload.token,
    expiresAtMs: payload.expires_at ? Date.parse(payload.expires_at) : Date.now() + 50 * 60_000,
  };
  return cachedInstallationToken.token;
}

export async function createGitHubIssue(input: { title: string; body: string; labels?: string[] }) {
  const response = await fetch(`https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/issues`, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${await installationToken()}`,
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "rtsai-feedback",
    },
    body: JSON.stringify(input),
  });
  const payload = await response.json() as { number?: number; html_url?: string; message?: string };
  if (!response.ok || !payload.number || !payload.html_url)
    throw new GitHubRequestError(response.status, payload.message || "GitHub issue creation failed");
  return { number: payload.number, htmlUrl: payload.html_url };
}
