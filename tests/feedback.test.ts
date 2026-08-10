import assert from "node:assert/strict";
import test from "node:test";
import { createFeedbackEmail, createFeedbackIssueBody, feedbackLabels, validateFeedbackPayload } from "../lib/feedback";

const valid = {
  category: "Mission Generator",
  rating: 4,
  title: "Preserve the main crossing",
  description: "The generated road network should preserve this crossing.",
  pagePath: "/?mission=riyadh",
  captures: [{ id: "capture-1", elementInfo: "button.generate — Generate mission", position: { x: 100, y: 200 } }],
  diagnostics: { metadata: { viewport: { width: 1440, height: 900 } } },
  clientSubmissionId: "7a82cb1e-7d34-4e5a-9b9d-8106391e1cd0",
  company: "",
};

test("validates and normalizes signed-in feedback payloads", () => {
  const result = validateFeedbackPayload(valid);
  assert.equal(result.ok, true);
  if (result.ok) {
    assert.equal(result.value.category, "Mission Generator");
    assert.equal(result.value.rating, 4);
    assert.equal(result.value.pagePath, "/");
    assert.equal(result.value.captures.length, 1);
  }
});

test("rejects spam, short descriptions, and unknown categories", () => {
  assert.equal(validateFeedbackPayload({ ...valid, company: "robots inc" }).ok, false);
  assert.equal(validateFeedbackPayload({ ...valid, description: "short" }).ok, false);
  assert.equal(validateFeedbackPayload({ ...valid, category: "billing" }).ok, false);
});

test("escapes feedback before rendering the Firebase mail alert", () => {
  const result = validateFeedbackPayload({ ...valid, description: "Please preserve <script>alert('x')</script> roads." });
  assert.equal(result.ok, true);
  if (!result.ok) return;
  const email = createFeedbackEmail({
    receipt: "RTS-ABC12345",
    issueNumber: 42,
    issueUrl: "https://github.com/alibad/RTSAI-Web/issues/42",
    receivedAt: "2026-08-10T10:00:00.000Z",
    submission: result.value,
    identity: { uid: "firebase-user", email: "player@example.com", name: "Player <One>" },
  });
  assert.doesNotMatch(email.html, /<script>/);
  assert.match(email.html, /&lt;script&gt;/);
  assert.match(email.html, /Player &lt;One&gt;/);
});

test("creates a complete Firebase mail fallback without a GitHub issue", () => {
  const result = validateFeedbackPayload(valid);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  const email = createFeedbackEmail({
    receipt: "RTS-ABC12345",
    receivedAt: "2026-08-10T10:00:00.000Z",
    submission: result.value,
    identity: { uid: "firebase-user", email: "player@example.com", name: "Player" },
  });
  assert.match(email.html, /Delivered directly through Firebase mail/);
  assert.match(email.text, /Private issue: pending synchronization/);
  assert.match(email.text, /button\.generate/);
  assert.match(email.text, /Firebase UID: firebase-user/);
});

test("creates a private issue body with bounded context and labels", () => {
  const result = validateFeedbackPayload(valid);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  const body = createFeedbackIssueBody({
    receipt: "RTS-ABC12345",
    receivedAt: "2026-08-10T10:00:00.000Z",
    pageUrl: "https://rtsai.net/",
    submission: result.value,
    identity: { uid: "firebase-user", email: "player@example.com", name: "Player" },
  });
  assert.match(body, /Selected elements/);
  assert.match(body, /button\.generate/);
  assert.deepEqual(feedbackLabels("Bug"), ["feedback", "source:web", "bug"]);
});
