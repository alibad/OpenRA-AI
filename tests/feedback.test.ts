import assert from "node:assert/strict";
import test from "node:test";
import { createFeedbackEmailHtml, validateFeedbackPayload } from "../lib/feedback";

const valid = {
  category: "mission-generator",
  rating: 4,
  message: "The generated road network should preserve this crossing.",
  pagePath: "/?mission=riyadh",
  clientSubmissionId: "7a82cb1e-7d34-4e5a-9b9d-8106391e1cd0",
  company: "",
};

test("validates and normalizes signed-in feedback payloads", () => {
  const result = validateFeedbackPayload(valid);
  assert.equal(result.ok, true);
  if (result.ok) {
    assert.equal(result.value.category, "mission-generator");
    assert.equal(result.value.rating, 4);
    assert.equal(result.value.pagePath, "/?mission=riyadh");
  }
});

test("rejects spam, short messages, and unknown categories", () => {
  assert.equal(validateFeedbackPayload({ ...valid, company: "robots inc" }).ok, false);
  assert.equal(validateFeedbackPayload({ ...valid, message: "short" }).ok, false);
  assert.equal(validateFeedbackPayload({ ...valid, category: "billing" }).ok, false);
});

test("escapes feedback before rendering the private email", () => {
  const result = validateFeedbackPayload({ ...valid, message: "Please preserve <script>alert('x')</script> roads." });
  assert.equal(result.ok, true);
  if (!result.ok) return;
  const html = createFeedbackEmailHtml({
    feedbackId: "RTS-ABC12345",
    receivedAt: "2026-08-10T10:00:00.000Z",
    submission: result.value,
    identity: { uid: "firebase-user", email: "player@example.com", name: "Player <One>" },
  });
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /Player &lt;One&gt;/);
});
