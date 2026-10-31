from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.database import check_database_connection, engine, initialize_database
from app.routes import admin_router, public_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="GrindPvP API",
        version="0.2.0",
        description="Ranked PvP profiles, leaderboards, match history, and admin tools.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://grindpvp-blsu.onrender.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(public_router)
    app.include_router(admin_router)

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        try:
            check_database_connection()
        except SQLAlchemyError as error:
            raise HTTPException(
                status_code=503,
                detail="Database connection is unavailable.",
            ) from error

        return {
            "status": "ok",
            "database": "connected",
            "database_engine": engine.dialect.name,
        }

    return app


app = create_app()
