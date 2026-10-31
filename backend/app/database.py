from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Admin, Base, KitLock, RoleDefinition, TitleDefinition
from app.ranking import KIT_IDS, ROLE_COLORS, TITLE_COLORS


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


engine = create_database_engine(get_settings().sqlalchemy_database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def check_database_connection() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def validate_database_configuration() -> None:
    settings = get_settings()
    if settings.is_production and engine.dialect.name != "postgresql":
        raise RuntimeError(
            "Production requires PostgreSQL. Configure DATABASE_URL with the existing Render database connection."
        )


def initialize_database() -> None:
    from app.security import hash_password

    settings = get_settings()
    validate_database_configuration()
    if settings.admin_password and not settings.admin_password.strip():
        raise RuntimeError("ADMIN_PASSWORD must not be blank.")

    Base.metadata.create_all(engine)
    with SessionLocal.begin() as session:
        for kit in KIT_IDS:
            if session.get(KitLock, kit) is None:
                session.add(KitLock(kit=kit))
        for name, color in ROLE_COLORS.items():
            if session.get(RoleDefinition, name) is None:
                session.add(RoleDefinition(name=name, color=color))
        for name, color in TITLE_COLORS.items():
            if session.get(TitleDefinition, name) is None:
                session.add(TitleDefinition(name=name, color=color))

        if settings.admin_password:
            admin = session.get(Admin, settings.admin_username)
            password_hash = hash_password(settings.admin_password)
            if admin is None:
                session.add(Admin(username=settings.admin_username, password_hash=password_hash))
            else:
                admin.password_hash = password_hash