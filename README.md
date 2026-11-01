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

### Free encrypted file backups

For a free Render web service using SQLite, the backend keeps an encrypted
database snapshot on a separate `database-backups` branch in the existing
GitHub repository. It restores the latest snapshot during startup and updates
the snapshot after each database write. Render deploys `main`, so snapshot
commits on the backup branch do not trigger another deployment. SQLite on
Render itself is still temporary; the encrypted GitHub copy is the recovery
source.

Set these Render environment variables before deploying:

- `BACKUP_REPOSITORY` to `owner/repository` (for this project:
  `goofarc-a11y/grindpvp-backend`)
- `BACKUP_TOKEN` to a fine-grained GitHub token limited to this repository
  with Contents read/write permission
- `BACKUP_ENCRYPTION_KEY` to a URL-safe base64-encoded random 32-byte key

Generate the encryption key locally with:

```powershell
py -3 -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Save the key and token as Render secrets; never commit them or send them in
chat. The database contents are AES-GCM encrypted before upload, including
password hashes and player data; the backup branch is visible because this
repository is public, but it contains ciphertext only. Keep a safe copy of the
encryption key: without it, backups cannot be restored. Production startup
refuses to run SQLite without all three backup settings, and fails rather than
silently starting with an unreadable or corrupt backup. GitHub API limits and
the 50 MB database limit apply; if a backup upload fails, the write request
returns an error and logs must be checked before retrying.

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
