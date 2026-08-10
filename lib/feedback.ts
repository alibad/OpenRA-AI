export const feedbackCategories = [
  "idea",
  "bug",
  "gameplay",
  "mission-generator",
  "ai-companion",
  "website",
  "other",
] as const;

export type FeedbackCategory = (typeof feedbackCategories)[number];

export type FeedbackSubmission = {
  category: FeedbackCategory;
  rating: number | null;
  message: string;
  pagePath: string | null;
  clientSubmissionId: string;
};

type ValidationResult =
  | { ok: true; value: FeedbackSubmission }
  | { ok: false; error: string };

function cleanText(value: unknown, maxLength: number) {
  if (typeof value !== "string") return "";
  return value.replace(/\r\n?/g, "\n").trim().slice(0, maxLength + 1);
}

export function validateFeedbackPayload(input: unknown): ValidationResult {
  if (!input || typeof input !== "object") return { ok: false, error: "Invalid feedback" };
  const record = input as Record<string, unknown>;

  // A filled honeypot is treated as spam without revealing the trigger.
  if (cleanText(record.company, 100)) return { ok: false, error: "Unable to send feedback" };

  const category = cleanText(record.category, 40);
  if (!feedbackCategories.includes(category as FeedbackCategory))
    return { ok: false, error: "Choose a feedback category" };

  const message = cleanText(record.message, 2_000);
  if (message.length < 10) return { ok: false, error: "Add at least 10 characters" };
  if (message.length > 2_000) return { ok: false, error: "Keep feedback under 2,000 characters" };

  const rating = record.rating === null || record.rating === undefined || record.rating === ""
    ? null
    : Number(record.rating);
  if (rating !== null && (!Number.isInteger(rating) || rating < 1 || rating > 5))
    return { ok: false, error: "Rating must be between 1 and 5" };

  const clientSubmissionId = cleanText(record.clientSubmissionId, 80);
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(clientSubmissionId))
    return { ok: false, error: "Invalid feedback receipt" };

  const rawPath = cleanText(record.pagePath, 300);
  const pagePath = rawPath && rawPath.startsWith("/") && !rawPath.startsWith("//") ? rawPath : null;

  return {
    ok: true,
    value: {
      category: category as FeedbackCategory,
      rating,
      message,
      pagePath,
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

export function createFeedbackEmailHtml(input: {
  feedbackId: string;
  receivedAt: string;
  submission: FeedbackSubmission;
  identity: { uid: string; email: string | null; name: string | null };
}) {
  const { feedbackId, receivedAt, submission, identity } = input;
  const safeMessage = escapeHtml(submission.message).replace(/\n/g, "<br />");
  const rows = [
    ["Receipt", feedbackId],
    ["Received", receivedAt],
    ["Category", submission.category],
    ["Rating", submission.rating ? `${submission.rating} / 5` : "Not provided"],
    ["Page", submission.pagePath ?? "Not shared"],
    ["User", identity.name ?? "Not provided"],
    ["Email", identity.email ?? "Not provided"],
    ["Firebase UID", identity.uid],
  ];
  const details = rows.map(([label, value]) =>
    `<tr><th style="padding:8px 14px 8px 0;text-align:left;color:#73776f;font-size:12px">${escapeHtml(label)}</th><td style="padding:8px 0;color:#20231f;font-size:13px">${escapeHtml(value)}</td></tr>`,
  ).join("");

  return `<!doctype html><html><body style="margin:0;background:#f0eee6;color:#20231f;font-family:Arial,sans-serif"><div style="max-width:680px;margin:0 auto;padding:36px 24px"><p style="margin:0 0 8px;color:#c84631;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">RTS AI feedback</p><h1 style="margin:0 0 28px;font-size:30px">${escapeHtml(submission.category.replace(/-/g, " "))}</h1><div style="padding:22px;background:#fff;border:1px solid #d8d4c7;font-size:16px;line-height:1.6">${safeMessage}</div><table style="width:100%;margin-top:22px;border-collapse:collapse">${details}</table></div></body></html>`;
}
