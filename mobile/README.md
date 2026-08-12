# Aviva GeoPlan — Field Survey app (Expo / React Native)

Offline-first companion to GeoPlan. Surveyors capture **GPS-located** manholes
(with condition + photos/videos) and update buildings (type, address, units) in
the field with no signal; everything queues locally and syncs to the GeoPlan API
when a connection returns.

## What it does now (Phase 2 scaffold)

- **JWT login** against the GeoPlan API (tokens stored in the device keychain).
- **GPS capture is central** — every manhole and every photo/video is stamped
  with a coordinate and its accuracy (colour-coded: green ≤10 m, amber ≤25 m,
  red beyond).
- **Map** (react-native-maps) — shows your position and your captured pins
  (manholes navy, handholes blue) and routes (teal synced / amber pending).
- **Drop-a-pin placement** — pick "Manhole pin" or "Handhole pin", tap the map
  to place it at that exact coordinate, choose a condition, save (queued).
- **Walk-to-record cable routes** — tap "Record route" and walk the path; the
  app logs a GPS point roughly every 8 m and draws the line live. Stop to save
  the polyline (queued); the API measures its true length in the metric CRS.
- **Manhole capture** (form) — GPS fix, type, condition, notes, photo/video → queued.
- **Building update** — "find buildings near me" (GPS → nearest list), pick one,
  update type/address/units → queued.
- **Offline outbox + sync** — captures persist in on-device SQLite and replay to
  the API idempotently (client-generated ids, so a replayed capture never
  duplicates). Media uploads go straight to MinIO via presigned URLs.
- Online/offline indicator and a pending count.

## Prerequisites

- Node 18+, and the Expo tooling: `npm i -g expo` (or use `npx`).
- The GeoPlan API running and reachable from the phone.

## Configure

1. In `src/config.ts` set `API_BASE` to your dev machine's **LAN IP** (not
   `localhost`), e.g. `http://192.168.1.20:8000`. The phone and the machine must
   be on the same network.
2. On the API, set `MINIO_PUBLIC_ENDPOINT` to the same host, port `9010`
   (e.g. `192.168.1.20:9010`) so presigned media URLs are reachable from the
   phone. Rebuild/restart the API after adding the `minio` dependency and run
   `make migrate` (migration `0011`).

## Maps

The map uses `react-native-maps`. On **iOS** it works in Expo Go out of the box
(Apple Maps). On **Android** it needs a Google Maps API key — put it in
`app.json` under `android.config.googleMaps.apiKey` (replace the placeholder), or
the map will be blank. For production and background route recording, build a
dev client (`npx expo run:android` / `run:ios`) rather than Expo Go.

## Run

```
cd mobile
npm install
npm start          # then scan the QR with Expo Go (iOS/Android)
```

Sign in, paste your **project id** (from the web app URL) on the home screen,
then capture. Tap **Sync now** when you have signal.

## Architecture

- `src/db.ts` — SQLite: `outbox` (queued ops), `assets` (local cache), `kv`.
- `src/sync.ts` — replays the outbox: parents (manholes/buildings) first, then
  media once the parent has a server id.
- `src/gps.ts` — permission + high-accuracy fix.
- `src/auth.ts` — login, keychain token storage, refresh-and-retry.
- `src/screens/` — Login, Home, Manhole, Building.

## Web / PWA (Netlify)

A PWA build of this app exists so you can install it on a phone straight
from a browser, no app store or dev client needed. It reuses almost every
screen as-is; two pieces are swapped for web-only implementations because
their native modules don't run in a browser:

- **Map** — `react-native-maps` has no working web build (confirmed: it
  pulls in native codegen internals that fail to bundle). `src/screens/MapScreen.web.tsx`
  reimplements the same pin-drop / route-recording UI with MapLibre GL JS
  over free OpenStreetMap raster tiles — no API key needed.
- **Offline store** — `expo-sqlite`'s modern async API has no browser
  implementation in this Expo version. `src/db.web.ts` reimplements the
  same functions over IndexedDB. The outbox/sync/GPS/auth logic is
  untouched; everything just calls `../db` and Metro resolves the right
  file per platform automatically.

Everything else (login, keychain-equivalent token storage, camera capture,
online/offline detection) already has browser support built into Expo's own
web target, so those files needed no changes.

### Build

```
cd mobile
npm install
npm run build:web
```

This runs `expo export --platform web` then patches the generated
`index.html` with the PWA tags Expo's web export doesn't add on its own
(manifest link, apple-touch-icon, iOS standalone-mode meta tags — see
`scripts/patch-pwa-html.js`). Output lands in `dist/`, ready to deploy as-is.

### Deploy to Netlify

**Fastest — Netlify Drop:** go to https://app.netlify.com/drop and drag the
`mobile/dist` folder in. You'll get a `*.netlify.app` URL in seconds.

**Or, git-linked / Netlify CLI:** `netlify.toml` is already set up (build
command, publish dir, SPA redirect, no-cache headers on `index.html`/`sw.js`
so updates always land instead of getting stuck cached on a phone).

### Before it's actually usable on your phone

1. **Point it at a reachable API.** The default in `src/config.ts` is a LAN
   IP (`192.168.1.236:8000`) — that only works on the same Wi-Fi as your
   dev machine. Open the installed PWA → sign-in screen → "Server settings"
   and set it to wherever the GeoPlan API is actually reachable from the
   *phone's* network (a deployed API, or a tunnel like ngrok/Cloudflare
   Tunnel/Tailscale pointed at your dev machine for testing).
2. **Add the Netlify URL to CORS.** In `infra/.env`, add your `*.netlify.app`
   URL to `ALLOWED_ORIGINS` (comma-separated with the existing frontend
   origin), then restart the API.
3. **Install it.** Open the Netlify URL on the phone in Safari (iOS) or
   Chrome (Android), then *Share → Add to Home Screen* (iOS) or the
   install prompt / menu → *Install app* (Android).

### Known limitations vs. the native app

- **iOS Safari can evict IndexedDB** after roughly a week of the PWA not
  being opened (Apple's anti-tracking storage policy, not a bug here) —
  sync often rather than trusting it as long-term storage the way the
  native app's SQLite file is.
- **No background route recording.** `watchRoute` only runs while the tab
  is open and the screen is on — there's no web equivalent of native
  background location.
- **Camera capture is a file picker**, not the native camera UI — usually
  still opens the camera directly on a phone, just with the browser's
  chrome around it.
- **No true background sync.** "Sync now" is manual, same as Expo Go on
  native without a dev client.

## Not yet (roadmap)

- A map view (react-native-maps) to place/select assets visually.
- Street and corridor capture (same outbox pattern).
- Background upload of large video on Wi‑Fi only; a dev build (not Expo Go) is
  needed for true background transfer.
- Conflict UI for server-vs-field edits (today: last-writer-wins + provenance).
