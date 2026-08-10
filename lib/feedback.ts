export const feedbackCategories = [
  "Bug",
  "Feature Request",
  "UI/UX",
  "Gameplay",
  "Mission Generator",
  "AI Companion",
  "General",
] as const;

export type FeedbackCategory = (typeof feedbackCategories)[number];

export type FeedbackCapture = {
  id: string;
  elementInfo: string;
  position: { x: number; y: number };
};

export type FeedbackConsoleEntry = {
  level: "log" | "warn" | "error" | "info";
  message: string;
  timestamp: string;
};

export type FeedbackNetworkEntry = {
  method: string;
  url: string;
  status: number;
  durationMs: number;
  timestamp: string;
};

export type FeedbackBrowserMetadata = {
  viewport?: { width: number; height: number };
  screen?: { width: number; height: number };
  devicePixelRatio?: number;
  language?: string;
  platform?: string;
  cookiesEnabled?: boolean;
  onLine?: boolean;
  connection?: { effectiveType?: string; downlink?: number; rtt?: number };
};

export type FeedbackSubmission = {
  title: string;
  description: string;
  category: FeedbackCategory;
  rating: number | null;
  pagePath: string | null;
  captures: FeedbackCapture[];
  diagnostics: {
    metadata?: FeedbackBrowserMetadata;
    console?: FeedbackConsoleEntry[];
    network?: FeedbackNetworkEntry[];
  };
  clientSubmissionId: string;
};

type ValidationResult =
  | { ok: true; value: FeedbackSubmission }
  | { ok: false; error: string };

function cleanText(value: unknown, maxLength: number) {
  if (typeof value !== "string") return "";
  return value.replace(/\r\n?/g, "\n").trim().slice(0, maxLength + 1);
}

function finiteNumber(value: unknown, min: number, max: number) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(max, Math.max(min, number)) : null;
}

function validTimestamp(value: unknown) {
  const text = cleanText(value, 40);
  return Number.isNaN(Date.parse(text)) ? new Date(0).toISOString() : text;
}

function validateCaptures(value: unknown): FeedbackCapture[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 10).flatMap((item, index) => {
    if (!item || typeof item !== "object") return [];
    const capture = item as Record<string, unknown>;
    const position = capture.position && typeof capture.position === "object"
      ? capture.position as Record<string, unknown>
      : {};
    const elementInfo = cleanText(capture.elementInfo, 500);
    const x = finiteNumber(position.x, 0, 20_000);
    const y = finiteNumber(position.y, 0, 20_000);
    if (!elementInfo || x === null || y === null) return [];
    return [{
      id: cleanText(capture.id, 100) || `capture-${index + 1}`,
      elementInfo,
      position: { x: Math.round(x), y: Math.round(y) },
    }];
  });
}

function validateMetadata(value: unknown): FeedbackBrowserMetadata | undefined {
  if (!value || typeof value !== "object") return undefined;
  const metadata = value as Record<string, unknown>;
  const dimensions = (input: unknown) => {
    if (!input || typeof input !== "object") return undefined;
    const item = input as Record<string, unknown>;
    const width = finiteNumber(item.width, 0, 20_000);
    const height = finiteNumber(item.height, 0, 20_000);
    return width === null || height === null ? undefined : { width: Math.round(width), height: Math.round(height) };
  };
  const connectionInput = metadata.connection && typeof metadata.connection === "object"
    ? metadata.connection as Record<string, unknown>
    : null;
  const connection = connectionInput ? {
    effectiveType: cleanText(connectionInput.effectiveType, 30) || undefined,
    downlink: finiteNumber(connectionInput.downlink, 0, 10_000) ?? undefined,
    rtt: finiteNumber(connectionInput.rtt, 0, 100_000) ?? undefined,
  } : undefined;
  return {
    viewport: dimensions(metadata.viewport),
    screen: dimensions(metadata.screen),
    devicePixelRatio: finiteNumber(metadata.devicePixelRatio, 0.1, 20) ?? undefined,
    language: cleanText(metadata.language, 40) || undefined,
    platform: cleanText(metadata.platform, 100) || undefined,
    cookiesEnabled: typeof metadata.cookiesEnabled === "boolean" ? metadata.cookiesEnabled : undefined,
    onLine: typeof metadata.onLine === "boolean" ? metadata.onLine : undefined,
    connection,
  };
}

function validateConsole(value: unknown): FeedbackConsoleEntry[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const entries = value.slice(-100).flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const entry = item as Record<string, unknown>;
    const level = cleanText(entry.level, 10);
    const message = cleanText(entry.message, 2_000);
    if (!(["log", "warn", "error", "info"] as string[]).includes(level) || !message) return [];
    return [{ level: level as FeedbackConsoleEntry["level"], message, timestamp: validTimestamp(entry.timestamp) }];
  });
  return entries.length ? entries : undefined;
}

function validateNetwork(value: unknown): FeedbackNetworkEntry[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const entries = value.slice(-50).flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const entry = item as Record<string, unknown>;
    const url = cleanText(entry.url, 500);
    const method = cleanText(entry.method, 12).toUpperCase();
    const status = finiteNumber(entry.status, 0, 999);
    const durationMs = finiteNumber(entry.durationMs, 0, 600_000);
    if (!url || !method || status === null || durationMs === null) return [];
    return [{ method, url, status: Math.round(status), durationMs: Math.round(durationMs), timestamp: validTimestamp(entry.timestamp) }];
  });
  return entries.length ? entries : undefined;
}

export function validateFeedbackPayload(input: unknown): ValidationResult {
  if (!input || typeof input !== "object") return { ok: false, error: "Invalid feedback" };
  const record = input as Record<string, unknown>;
  if (cleanText(record.company, 100)) return { ok: false, error: "Unable to send feedback" };

  const category = cleanText(record.category, 40);
  if (!feedbackCategories.includes(category as FeedbackCategory))
    return { ok: false, error: "Choose a feedback category" };

  const title = cleanText(record.title, 120);
  if (title.length < 4) return { ok: false, error: "Add a short title" };
  if (title.length > 120) return { ok: false, error: "Keep the title under 120 characters" };

  const description = cleanText(record.description, 4_000);
  if (description.length < 10) return { ok: false, error: "Add at least 10 characters of detail" };
  if (description.length > 4_000) return { ok: false, error: "Keep feedback under 4,000 characters" };

  const rating = record.rating === null || record.rating === undefined || record.rating === ""
    ? null
    : Number(record.rating);
  if (rating !== null && (!Number.isInteger(rating) || rating < 1 || rating > 5))
    return { ok: false, error: "Rating must be between 1 and 5" };

  const clientSubmissionId = cleanText(record.clientSubmissionId, 80);
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(clientSubmissionId))
    return { ok: false, error: "Invalid feedback receipt" };

  const rawPath = cleanText(record.pagePath, 300).split(/[?#]/, 1)[0];
  const pagePath = rawPath && rawPath.startsWith("/") && !rawPath.startsWith("//") ? rawPath : null;
  const diagnosticsInput = record.diagnostics && typeof record.diagnostics === "object"
    ? record.diagnostics as Record<string, unknown>
    : {};

  return {
    ok: true,
    value: {
      title,
      description,
      category: category as FeedbackCategory,
      rating,
      pagePath,
      captures: validateCaptures(record.captures),
      diagnostics: {
        metadata: validateMetadata(diagnosticsInput.metadata),
        console: validateConsole(diagnosticsInput.console),
        network: validateNetwork(diagnosticsInput.network),
      },
      clientSubmissionId,
    },
  };
}

export function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character] ?? character);
}

function jsonBlock(value: unknown) {
  return `\n\n\`\`\`json\n${JSON.stringify(value, null, 2).slice(0, 12_000)}\n\`\`\``;
}

export function feedbackLabels(category: FeedbackCategory) {
  const categoryLabel: Partial<Record<FeedbackCategory, string>> = {
    "Bug": "bug",
    "Feature Request": "enhancement",
    "UI/UX": "ui/ux",
    "Gameplay": "gameplay",
    "Mission Generator": "mission-generator",
    "AI Companion": "ai-companion",
  };
  return ["feedback", "source:web", ...(categoryLabel[category] ? [categoryLabel[category]!] : [])];
}

export function createFeedbackIssueBody(input: {
  receipt: string;
  receivedAt: string;
  pageUrl: string;
  submission: FeedbackSubmission;
  identity: { uid: string; email: string | null; name: string | null };
}) {
  const { receipt, receivedAt, pageUrl, submission, identity } = input;
  const captures = submission.captures.length
    ? submission.captures.map((capture, index) => `${index + 1}. \`${capture.elementInfo}\` at viewport (${capture.position.x}, ${capture.position.y})`).join("\n")
    : "None selected.";
  let body = `**Page:** ${submission.pagePath ?? "/"}\n**URL:** ${pageUrl}\n\n## Feedback\n\n${submission.description}\n\n## Context\n\n- Category: ${submission.category}\n- Rating: ${submission.rating ? `${submission.rating}/5` : "Not provided"}\n- Submitted: ${receivedAt}\n- User: ${identity.name || "Not provided"}\n- Email: ${identity.email || "Not provided"}\n- Firebase UID: \`${identity.uid}\`\n\n## Selected elements\n\n${captures}`;
  if (submission.diagnostics.metadata) body += `\n\n## Browser metadata${jsonBlock(submission.diagnostics.metadata)}`;
  if (submission.diagnostics.console) body += `\n\n## Console diagnostics${jsonBlock(submission.diagnostics.console)}`;
  if (submission.diagnostics.network) body += `\n\n## Network diagnostics${jsonBlock(submission.diagnostics.network)}`;
  body += `\n\n<!-- ${receipt}; client:${submission.clientSubmissionId} -->`;
  return body.slice(0, 60_000);
}

export function createFeedbackEmail(input: {
  receipt: string;
  issueNumber?: number;
  issueUrl?: string;
  receivedAt: string;
  submission: FeedbackSubmission;
  identity: { uid: string; email: string | null; name: string | null };
}) {
  const { receipt, issueNumber, issueUrl, receivedAt, submission, identity } = input;
  const safeDescription = escapeHtml(submission.description).replace(/\n/g, "<br />");
  const safeTitle = escapeHtml(submission.title);
  const sender = escapeHtml(identity.name || identity.email || "Signed-in player");
  const captures = submission.captures.length
    ? submission.captures.map((capture) => `${capture.elementInfo} @ ${capture.position.x},${capture.position.y}`).join("\n")
    : "None";
  const diagnostics = Object.keys(submission.diagnostics).length
    ? JSON.stringify(submission.diagnostics, null, 2)
    : "Not included";
  const context = `Category: ${submission.category}\nRating: ${submission.rating ?? "Not provided"}\nPage: ${submission.pagePath || "/"}\nUser: ${identity.name || identity.email || "Signed-in player"}\nFirebase UID: ${identity.uid}\nReceipt: ${receipt}\n\nSelected elements:\n${captures}\n\nDiagnostics:\n${diagnostics}`;
  const issueAction = issueNumber && issueUrl
    ? `<p style="margin:28px 0 0"><a href="${escapeHtml(issueUrl)}" style="display:inline-block;padding:13px 18px;background:#ef5b3f;color:#fff;text-decoration:none;font-weight:700">Open private issue #${issueNumber}</a></p>`
    : `<p style="margin:28px 0 0;color:#b5b5aa;font-size:13px">Delivered directly through Firebase mail. GitHub issue synchronization is pending.</p>`;
  const html = `<!doctype html><html><body style="margin:0;background:#111411;color:#f0eee6;font-family:Arial,sans-serif"><div style="max-width:680px;margin:0 auto;padding:40px 24px"><p style="margin:0 0 8px;color:#ef5b3f;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">RTS AI feedback · ${escapeHtml(submission.category)}</p><h1 style="margin:0 0 10px;font-size:30px;line-height:1.15">${safeTitle}</h1><p style="margin:0 0 26px;color:#b5b5aa;font-size:13px">${sender} · ${escapeHtml(receivedAt)} · ${escapeHtml(receipt)}</p><div style="padding:22px;background:#f0eee6;color:#111411;border-left:4px solid #ef5b3f;font-size:16px;line-height:1.6">${safeDescription}</div><pre style="margin:24px 0 0;padding:18px;overflow:auto;background:#090b09;color:#d5d7cf;border:1px solid #343a34;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap">${escapeHtml(context)}</pre>${issueAction}</div></body></html>`;
  const issueLine = issueUrl ? `\nPrivate issue: ${issueUrl}` : "\nPrivate issue: pending synchronization";
  const text = `RTS AI feedback: ${submission.title}\n\n${submission.description}\n\n${context}${issueLine}`;
  return { html, text };
}
