import {
  createFeedbackEmail,
  createFeedbackIssueBody,
  feedbackLabels,
  validateFeedbackPayload,
} from "../../../lib/feedback";
import { mailGroup, sendFirebaseEmail } from "../../../lib/firebase-mail";
import { verifyFirebaseIdentity } from "../../../lib/firebase-token";
import { createGitHubIssue, GitHubRequestError, isGitHubConfigured } from "../../../lib/github";

const maxBodyBytes = 64_000;

function isAllowedOrigin(request: Request) {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  const configured = process.env.FEEDBACK_ALLOWED_ORIGINS?.split(",").map((value) => value.trim()).filter(Boolean) ?? [];
  const defaults = ["https://rtsai.net", "https://www.rtsai.net", "https://openra-ai.albertine.chatgpt.site"];
  return [...defaults, ...configured].includes(origin) || /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(origin);
}

export async function POST(request: Request) {
  if (!isAllowedOrigin(request)) return Response.json({ error: "Invalid request origin" }, { status: 403 });
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > maxBodyBytes) return Response.json({ error: "Feedback is too large" }, { status: 413 });

  const identity = await verifyFirebaseIdentity(request);
  if (!identity) return Response.json({ error: "Sign in required" }, { status: 401 });

  let input: unknown;
  try {
    input = await request.json();
  } catch {
    return Response.json({ error: "Invalid request" }, { status: 400 });
  }
  const parsed = validateFeedbackPayload(input);
  if (!parsed.ok) return Response.json({ error: parsed.error }, { status: 400 });

  const receivedAt = new Date().toISOString();
  const receipt = `RTS-${parsed.value.clientSubmissionId.slice(0, 8).toUpperCase()}`;
  const baseUrl = (process.env.NEXT_PUBLIC_APP_URL || "https://rtsai.net").replace(/\/$/, "");
  const pageUrl = `${baseUrl}${parsed.value.pagePath || "/"}`;
  const issueTitle = `[${parsed.value.category}] ${parsed.value.title} — ${parsed.value.pagePath || "/"}`.slice(0, 240);
  const issueBody = createFeedbackIssueBody({ receipt, receivedAt, pageUrl, submission: parsed.value, identity });
  const labels = feedbackLabels(parsed.value.category);

  let issue: { number: number; html_url: string } | null = null;
  if (isGitHubConfigured()) {
    try {
      try {
        const response = await createGitHubIssue({ title: issueTitle, body: issueBody, labels });
        issue = { number: response.number, html_url: response.htmlUrl };
      } catch (cause) {
        const status = cause instanceof GitHubRequestError ? cause.status : 0;
        if (status !== 422) throw cause;
        const response = await createGitHubIssue({ title: issueTitle, body: issueBody });
        issue = { number: response.number, html_url: response.htmlUrl };
      }
    } catch (cause) {
      const status = cause instanceof GitHubRequestError ? cause.status : 0;
      console.error("Private feedback issue creation failed", {
        status,
        name: cause instanceof Error ? cause.name : "UnknownError",
        message: cause instanceof Error ? cause.message.slice(0, 300) : "Unknown failure",
      });
    }
  }

  let notificationQueued = false;
  const administrator = process.env.FEEDBACK_ADMIN_EMAIL || mailGroup()[0];
  if (administrator) {
    const email = createFeedbackEmail({
      receipt,
      issueNumber: issue?.number,
      issueUrl: issue?.html_url,
      receivedAt,
      submission: parsed.value,
      identity,
    });
    try {
      await sendFirebaseEmail({
        to: administrator,
        subject: `[RTS AI] ${parsed.value.category}: ${parsed.value.title}`,
        html: email.html,
        text: email.text,
        auditToGroup: !mailGroup().includes(administrator),
      });
      notificationQueued = true;
    } catch (cause) {
      console.error("Firebase feedback notification failed", { issueNumber: issue?.number, cause: cause instanceof Error ? cause.message : "unknown" });
    }
  }

  if (!issue && !notificationQueued) {
    return Response.json(
      { error: "Feedback could not be saved. Your message is still here—please try again." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  return Response.json(
    {
      success: true,
      issueNumber: issue?.number,
      issueUrl: issue?.html_url,
      receipt: issue ? `RTS-#${issue.number}` : receipt,
      notificationQueued,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
