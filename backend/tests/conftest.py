from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import Admin, Base, KitLock, RoleDefinition, TitleDefinition
from app.ranking import KIT_IDS, ROLE_COLORS, TITLE_COLORS
from app.security import hash_password


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    from app import main, routes, security
    from app.config import Settings

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with test_sessions.begin() as session:
        session.add_all([KitLock(kit=kit) for kit in KIT_IDS])
        session.add_all([RoleDefinition(name=name, color=color) for name, color in ROLE_COLORS.items()])
        session.add_all([TitleDefinition(name=name, color=color) for name, color in TITLE_COLORS.items()])
        session.add(Admin(username="admin", password_hash=hash_password("1302")))

    def override_get_db():
        with test_sessions() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(main, "initialize_database", lambda: None)
    settings = Settings(
        admin_password="1302",
        admin_session_hours=2,
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
