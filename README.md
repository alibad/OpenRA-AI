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
- download the generated map without creating an account.

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
