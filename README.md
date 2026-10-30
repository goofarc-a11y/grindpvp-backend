# GrindPvP Backend

FastAPI service foundation. SQLite is the local-development default; configure
`DATABASE_URL` with a PostgreSQL URL for deployment. PostgreSQL URLs using
either `postgres://` or `postgresql://` are normalized to the psycopg 3 driver.

## Local setup

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload
```

The `/health` endpoint runs a database query and responds with HTTP 503 if the
database is unavailable. Ranked endpoints, database models, and migrations are
not part of this foundation milestone.

## Tests

```powershell
python -m pytest
```
