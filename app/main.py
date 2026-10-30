from fastapi import FastAPI, HTTPException

from app.database import check_database_connection

app = FastAPI(
    title="GrindPvP API",
    version="0.1.0",
    description="Backend foundation for the GrindPvP Fabric client.",
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    try:
        check_database_connection()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Database connection is unavailable.",
        ) from error

    return {"status": "ok", "database": "connected"}
