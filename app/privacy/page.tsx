import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy — RTS AI",
  description: "How RTS AI handles account identity and product analytics.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <main className="privacy-page">
      <Link className="privacy-back" href="/">← Back to RTS AI</Link>
      <span className="eyebrow">Privacy / plain language</span>
      <h1>Your identity is for your account—not ad targeting.</h1>
      <p className="privacy-lede">RTS AI uses Firebase Authentication to create your account and Google Analytics to understand whether the product is useful.</p>

      <section>
        <h2>Account data</h2>
        <p>When you sign up, Firebase Authentication stores your name, email address, encrypted credential information, account identifier, and basic account timestamps. We use that information to sign you in, address you in the interface, secure AI features, and support your account.</p>
      </section>
      <section>
        <h2>Usage analytics</h2>
        <p>Feature events can be associated with your pseudonymous Firebase user ID. We do not send your name, email, free-text mission prompt, search query, or exact latitude and longitude to Google Analytics.</p>
      </section>
      <section>
        <h2>Product feedback</h2>
        <p>Feedback you deliberately submit is delivered privately by email with your Firebase account identity so we can reply. The written message is never sent to Google Analytics; analytics receives only its category and optional rating.</p>
      </section>
      <section>
        <h2>Your controls</h2>
        <p>You can sign out at any time from the account menu. Account deletion and data-export controls will be added before the service leaves alpha.</p>
      </section>
      <section>
        <h2>Public downloads</h2>
        <p>Browsing the marketing site and downloading public game builds do not require an RTS AI account. Generating a mission or using interactive AI surfaces does.</p>
      </section>
    </main>
  );
}
