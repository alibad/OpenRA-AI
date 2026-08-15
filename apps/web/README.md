# OpenRA AI web

The public product site, browser mission studio, and game-download surface for
OpenRA AI.

Players can:

- download versioned macOS and Windows builds and their SHA-256 checksums;
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

## Game downloads

`lib/release.ts` is the single release manifest used by the page and mission
studio. Update its versions, download URLs, and checksum URLs only after each
matching package has passed the repository's local package smoke test and has
been uploaded as a GitHub Release asset.

Do not commit game ZIPs to the web app. Release assets belong in GitHub Releases
or equivalent object storage so the website can remain a small, independently
deployable application.

## Deployment boundary

The app does not require a database, user account, hosted build workflow, or
model-provider credential. It can remain in this monorepo or be extracted into
a separate `OpenRA-AI-Web` repository later. In either case, it should consume
published release metadata rather than depending on the local engine checkout.
