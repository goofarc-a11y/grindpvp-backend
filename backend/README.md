# GrindPvP Backend

FastAPI service for registered players, ranked kits, public verified-player
leaderboards, match history, and authenticated administration.

## Render deployment

The Render Blueprint is in `render.yaml` and is configured for the `backend`
directory. It creates a PostgreSQL database and web service. Set
`ADMIN_PASSWORD` in Render's environment settings before relying on admin
functions. The client signs in with the password only; the backend uses its
internal `admin` account by default. Passwords are scrypt-hashed before
storage, and failed login attempts are rate-limited per client IP. Configure
the desired password as a Render environment secret; do not put it in the
client or source code.

For an existing Render service, set:

- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`
- `APP_ENV=production`
- `DATABASE_URL` to the Render PostgreSQL internal connection string
- `ADMIN_PASSWORD` to the password accepted by the password-only login form

Render deploys the source connected to its Git repository. Push these changes
to that repository or trigger a deploy after updating the source; changing
files in a local workspace does not modify an already running Render service.

## Local setup

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload
```

Set `DATABASE_URL` to `sqlite:///./grindpvp.db` for local development or a
PostgreSQL SQLAlchemy URL for PostgreSQL. Admin login is disabled until
`ADMIN_PASSWORD` is set. Public self-registration is disabled
because a client-supplied UUID does not prove Minecraft account ownership; an
administrator can add the player by current Minecraft name. New names are
resolved to UUIDs through Mojang's official profile service; existing UUID
based admin requests remain supported. This lookup confirms the profile exists
but does not prove account ownership.

## API

- `GET /health`, `GET /catalog`
- `GET /players?search=&page=&page_size=`; `POST /players` is intentionally
  rejected until trusted Minecraft account verification is implemented
- `GET /players/{uuid}/stats`, `GET /profiles/{uuid}`
- `GET /players/presentation?page=&page_size=` returns name-decoration data
  for verified players only
- `GET /leaderboard/overall`, `GET /leaderboard/{kit}`
- `GET /matches`, `GET /matches/{uuid}`
- `POST /admin/login`, then pass the returned bearer token to admin endpoints
- `POST /admin/logout`, `/players`, `/verify`, `/roles`, `/titles`, `/matches`,
  `/tiers`, `/stats`; `GET /admin/matches`, `/logs`, `/players/{uuid}`

Admin create, verify, role, title, tier, statistics, and match operations accept
Minecraft names. New player creation resolves the official UUID server-side;
all previous UUID-based write payloads remain accepted for compatibility.

Public match submissions are rejected. Only the authenticated admin match
endpoint can update results. Match idempotency keys, a per-kit database lock,
and a unique HT1-per-kit index protect ranked updates. The database schema is
created at startup; production migrations are a follow-up before schema changes
are deployed.

## Tests

```powershell
python -m pytest
```
