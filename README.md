# RTS AI web

Private product website for [rtsai.net](https://rtsai.net). It markets and
distributes OpenRA AI while keeping the game engine and downloadable binaries
in the public [`alibad/OpenRA-AI`](https://github.com/alibad/OpenRA-AI)
repository.

Players can:

- download the newest published Windows build and its SHA-256 checksum;
- select a point on an OpenStreetMap basemap;
- translate nearby roads and waterways into a validated Red Alert `.oramap`;
- download the generated map without creating an account.

## Run locally

Node.js 22.13 or newer is required.

```powershell
npm install
npm run dev
```

Validate the production build with:

```powershell
npm run lint
npm test
```

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
