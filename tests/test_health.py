import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy import text

from app import main
from app.config import Settings
from app.database import create_database_engine


def test_health_returns_success_when_database_is_available(monkeypatch) -> None:
    monkeypatch.setattr(main, "check_database_connection", lambda: None)
    monkeypatch.setattr(main, "initialize_database", lambda: None)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_health_returns_service_unavailable_when_database_fails(monkeypatch) -> None:
    def fail_connection() -> None:
        raise OperationalError("SELECT 1", {}, RuntimeError("connection failed"))

    monkeypatch.setattr(main, "check_database_connection", fail_connection)
    monkeypatch.setattr(main, "initialize_database", lambda: None)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database connection is unavailable."


def test_sqlite_database_engine_can_execute_queries() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_postgres_urls_use_psycopg_driver() -> None:
    assert Settings(database_url="postgres://db.example/grindpvp").sqlalchemy_database_url == (
        "postgresql+psycopg://db.example/grindpvp"
    )
    assert Settings(database_url="postgresql://db.example/grindpvp").sqlalchemy_database_url == (
        "postgresql+psycopg://db.example/grindpvp"
    )


@pytest.mark.parametrize("path", ["/catalog", "/leaderboard/overall", "/health"])
def test_official_website_get_responses_include_cors_headers(client, monkeypatch, path: str) -> None:
    monkeypatch.setattr(main, "check_database_connection", lambda: None)

    response = client.get(path, headers={"Origin": "https://grindpvp-blsu.onrender.com"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://grindpvp-blsu.onrender.com"
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize("path", ["/catalog", "/leaderboard/overall", "/health"])
def test_official_website_preflight_succeeds_for_api_gets(client, path: str) -> None:
    response = client.options(
        path,
        headers={
            "Origin": "https://grindpvp-blsu.onrender.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://grindpvp-blsu.onrender.com"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_official_website_error_response_includes_cors_headers(client) -> None:
    response = client.get(
        "/profiles/not-a-uuid",
        headers={"Origin": "https://grindpvp-blsu.onrender.com"},
    )

    assert response.status_code == 422
    assert response.headers["access-control-allow-origin"] == "https://grindpvp-blsu.onrender.com"


@pytest.mark.parametrize("path", ["/catalog", "/leaderboard/overall", "/health"])
def test_foreign_origin_does_not_receive_cors_access(client, path: str) -> None:
    origin = "https://attacker.example"

    response = client.get(path, headers={"Origin": origin})
    preflight = client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers
