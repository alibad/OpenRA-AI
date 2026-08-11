# RTS AI web application guidance

- Build and refine the website directly in Next.js; Figma is not part of this product workflow.
- Treat the site as the public entry point for the whole RTS AI platform, not a hard-coded status page for one mod or release.
- Keep the homepage concise: product promise, the two core experiences, current playable proof, and a clear download path.
- Put detailed Companion, Mission Studio, platform, and download material on focused routes.
- Preserve server/client component boundaries and validate changes with local lint, tests, and production builds.
- Never add GitHub Actions or hosted workflow files.
