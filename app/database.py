from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.github_backup import (
    BackupError,
    backup_is_configured,
    restore_sqlite,
    save_sqlite,
    validate_backup_settings,
)
from app.models import Admin, Base, KitLock, RoleDefinition, TitleDefinition
from app.ranking import KIT_IDS, ROLE_COLORS, TITLE_COLORS


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


engine = create_database_engine(get_settings().sqlalchemy_database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Session, "do_orm_execute")
def mark_bulk_database_changes(state) -> None:
    if state.is_insert or state.is_update or state.is_delete:
        state.session.info["database_changed"] = True


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        try:
            yield session
            bulk_database_changed = session.info.pop("database_changed", False)
            database_changed = bool(
                session.new
                or session.dirty
                or session.deleted
                or bulk_database_changed
            )
            session.commit()
            settings = get_settings()
            if (
                database_changed
                and backup_is_configured(settings)
                and engine.dialect.name == "sqlite"
            ):
                save_sqlite(engine, settings)
        except Exception:
            session.rollback()
            raise


def check_database_connection() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def initialize_database() -> None:
    from app.security import hash_password

    settings = get_settings()
    uses_sqlite = engine.dialect.name == "sqlite"
    if settings.is_production and uses_sqlite and not backup_is_configured(settings):
        raise RuntimeError(
            "Production SQLite requires BACKUP_REPOSITORY, BACKUP_TOKEN, and BACKUP_ENCRYPTION_KEY."
        )
    if backup_is_configured(settings):
        if not uses_sqlite:
            raise RuntimeError("GitHub file backups can only be used with SQLite.")
        try:
            validate_backup_settings(settings)
            restore_sqlite(engine, settings)
        except BackupError as error:
            raise RuntimeError(
                f"Could not restore the encrypted GitHub database backup: {error}"
            ) from error
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
    if backup_is_configured(settings):
        try:
            save_sqlite(engine, settings)
        except BackupError as error:
            raise RuntimeError(f"Could not save the encrypted GitHub database backup: {error}") from error