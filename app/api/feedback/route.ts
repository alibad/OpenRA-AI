import { createFeedbackEmailHtml, validateFeedbackPayload } from "../../../lib/feedback";
import { verifyFirebaseIdentity } from "../../../lib/firebase-token";

const maxBodyBytes = 12_000;

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

  const apiKey = process.env.RESEND_API_KEY;
  const recipient = process.env.FEEDBACK_TO_EMAIL;
  if (!apiKey || !recipient) {
    console.error("Feedback delivery is missing required server configuration");
    return Response.json({ error: "Feedback delivery is temporarily unavailable" }, { status: 503 });
  }

  const feedbackId = `RTS-${crypto.randomUUID().slice(0, 8).toUpperCase()}`;
  const receivedAt = new Date().toISOString();
  const from = process.env.FEEDBACK_FROM_EMAIL || "RTS AI Feedback <onboarding@resend.dev>";
  const rating = parsed.value.rating ? ` · ${parsed.value.rating}/5` : "";
  const sender = identity.name || identity.email || "signed-in player";

  try {
    const delivery = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        "Idempotency-Key": `rtsai-feedback-${identity.uid}-${parsed.value.clientSubmissionId}`,
      },
      body: JSON.stringify({
        from,
        to: [recipient],
        ...(identity.email ? { reply_to: identity.email } : {}),
        subject: `[${feedbackId}] ${parsed.value.category}${rating} — ${sender}`,
        html: createFeedbackEmailHtml({ feedbackId, receivedAt, submission: parsed.value, identity }),
        text: `${parsed.value.message}\n\nReceipt: ${feedbackId}\nCategory: ${parsed.value.category}\nRating: ${parsed.value.rating ?? "Not provided"}\nPage: ${parsed.value.pagePath ?? "Not shared"}\nUser: ${sender}\nUID: ${identity.uid}`,
      }),
    });
    if (!delivery.ok) {
      console.error("Feedback delivery failed", { status: delivery.status, feedbackId });
      return Response.json({ error: "Feedback delivery is temporarily unavailable" }, { status: 503 });
    }
  } catch {
    console.error("Feedback delivery request failed", { feedbackId });
    return Response.json({ error: "Feedback delivery is temporarily unavailable" }, { status: 503 });
  }

  return Response.json({ ok: true, id: feedbackId }, { headers: { "Cache-Control": "no-store" } });
}
