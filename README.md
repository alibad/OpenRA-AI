# RTS AI web

Private product website for [rtsai.net](https://rtsai.net). It markets and
distributes OpenRA AI while keeping the game engine and downloadable binaries
in the public [`alibad/OpenRA-AI`](https://github.com/alibad/OpenRA-AI)
repository.

Players can:

- download the newest published Windows build and its SHA-256 checksum;
- search or select a point on an OpenStreetMap basemap;
- choose the Earth footprint and OpenRA battlefield size;
- translate live nearby roads and waterways into a validated Red Alert `.oramap`;
- share a complete mission setup with a copyable URL and generate new seeded variations;
- create a Firebase-backed commander profile before generating or downloading a new mission;
- use privacy-safe product analytics that associate events with a pseudonymous account ID instead of a name or email.
- send authenticated, private product feedback with a searchable receipt ID and optional usefulness rating.

The homepage also includes an interactive companion preview so visitors can
understand the pause, ask, and alert-priority experience before downloading the
game.

## Run locally

Node.js 22.13 or newer is required.

```powershell
npm install
npm run dev
```

Open `http://localhost:3000`. Location search and Earth feature acquisition are
proxied through the site's `/api/geocode` and `/api/earth-features` routes, so
the browser never needs to call public map services directly. No API key is
required for the website's map generator.

Copy `.env.example` to `.env.local` and fill in the public Firebase web-app
configuration. Email/password authentication must be enabled in Firebase and
`localhost`, `127.0.0.1`, `rtsai.net`, and any preview hostname must be listed as
authorized domains. Firebase's web configuration is public routing metadata;
never put Admin SDK credentials or service-account keys in `NEXT_PUBLIC_*`
variables.

Browsing, map exploration, and public game downloads remain open. Mission
compilation and companion interactions require a signed-in account. Google
Analytics is enabled automatically. It uses the Firebase UID and deliberately excludes names, email addresses, search text,
mission text, and exact coordinates.

The mission UI sends the current Firebase ID token to `/api/earth-features`.
That endpoint verifies the token signature, audience, and issuer against
Google's published Firebase keys before it requests Earth geometry. The client
gate is therefore backed by an API authorization boundary.

The global Feedback button uses the same signed-in identity. `/api/feedback`
validates the Firebase ID token, limits and sanitizes the submitted text, and
delivers it privately through Resend. Configure the server-only
`RESEND_API_KEY`, `FEEDBACK_TO_EMAIL`, and `FEEDBACK_FROM_EMAIL` variables from
`.env.example`. Written feedback never enters Google Analytics; only the
selected category and optional 1–5 rating are recorded as product events.

Validate the production build with:

```powershell
npm run lint
npm test
```

`npm test` type-checks the full project, builds the production worker, verifies
the rendered product surface and share-link parser, checks the API validation
boundary, and compiles a deterministic OpenRA map fixture.

## Release boundary

The site reads public GitHub Release metadata at runtime and falls back to a
known-good package when GitHub is temporarily unavailable. Do not commit game
ZIPs here. Game packages, checksums, source, and GPL obligations remain in the
public game repository.

Download links carry provider-neutral event attributes so private analytics can
be connected later without coupling the website to a specific vendor.

## Deployment

The production site is published through OpenAI Sites. Its custom domain is
`rtsai.net`; runtime values and analytics credentials belong in the host's
environment settings, never in source control.

There are no GitHub Actions or hosted release workflows in this repository.
