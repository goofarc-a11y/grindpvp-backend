# GrindPvP Website

Responsive React + TypeScript web client for the existing GrindPvP backend.
It does not create a website database: player, ranking, match, role, title,
verification, and audit data all come from the same API and configured database
as the Minecraft mod.

## Run locally

From this directory:

```powershell
npm install
npm run dev
```

Vite proxies `/api` requests to the same backend host used by the mod. To point
the development proxy at a different backend, create `.env.local` and set
`GRINDPVP_API_TARGET` to its HTTPS URL (or localhost during local development).

## Production setup

Build with `npm run build`. Configure `VITE_API_BASE_URL` to the backend's HTTPS
base URL when building the website. Add the website's exact origin to the
backend's comma-separated `CORS_ORIGINS` setting, then deploy the backend and
website. See `../backend/README.md` for the backend deployment and PostgreSQL
configuration.

The root `render.yaml` defines the `grindpvp-website` static site alongside
the existing backend and PostgreSQL resource. Connect the repository root to
Render as a Blueprint; the website build uses `npm ci && npm run build` and
publishes `Website/dist`. The expected origins are configured there:
`https://grindpvp-blsu.onrender.com` for the website and
`https://grindpvp-backend-1.onrender.com` for its API. If Render assigns a
different website hostname, update `CORS_ORIGINS` in the backend environment
to the exact website origin and redeploy the backend.

The browser sends admin passwords only to the backend's existing
`POST /admin/login` endpoint over HTTPS. The access code is not included in
frontend source or saved by the website; only the backend-issued bearer session
is kept in the current browser tab and revoked on sign-out. Set the backend's
`ADMIN_PASSWORD` to the existing access code in the backend deployment's secret
settings if it is not already configured there.

The My Profile page lets a player select their verified Minecraft username.
That UUID is remembered locally in the browser; it is not an account login or
proof of ownership. Profile skins are requested by the displayed profile's
UUID, never by the visitor's identity.

Animation, audio, and volume preferences are local to the browser. The skin
preview uses the public `mc-heads.net` rendering endpoint with the selected
player UUID.
