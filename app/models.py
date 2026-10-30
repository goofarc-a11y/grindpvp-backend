from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        Index("uq_players_username_case_insensitive", text("lower(username)"), unique=True),
    )

    uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(16), index=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    role_name: Mapped[str | None] = mapped_column(ForeignKey("roles.name"), nullable=True)
    title_name: Mapped[str | None] = mapped_column(ForeignKey("titles.name"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    kits: Mapped[list["PlayerKit"]] = relationship(back_populates="player", cascade="all, delete-orphan")


class PlayerKit(Base):
    __tablename__ = "player_kits"
    __table_args__ = (
        UniqueConstraint("player_uuid", "kit", name="uq_player_kit"),
        Index("ix_player_kits_kit_tier", "kit", "tier"),
        Index(
            "uq_player_kits_one_ht1_per_kit",
            "kit",
            unique=True,
            postgresql_where=text("tier = 'HT1'"),
            sqlite_where=text("tier = 'HT1'"),
        ),
    )

    player_uuid: Mapped[str] = mapped_column(ForeignKey("players.uuid", ondelete="CASCADE"), primary_key=True)
    kit: Mapped[str] = mapped_column(String(24), primary_key=True)
    tier: Mapped[str] = mapped_column(String(8), default="Unranked", nullable=False)
    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    loss_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    equal_tier_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ht1_defeated: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    player: Mapped[Player] = relationship(back_populates="kits")


class KitLock(Base):
    __tablename__ = "kit_locks"

    kit: Mapped[str] = mapped_column(String(24), primary_key=True)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_matches_idempotency_key"),
        Index("ix_matches_kit_created", "kit", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    kit: Mapped[str] = mapped_column(String(24), nullable=False)
    winner_uuid: Mapped[str] = mapped_column(ForeignKey("players.uuid"), nullable=False)
    loser_uuid: Mapped[str] = mapped_column(ForeignKey("players.uuid"), nullable=False)
    winner_tier_before: Mapped[str] = mapped_column(String(8), nullable=False)
    loser_tier_before: Mapped[str] = mapped_column(String(8), nullable=False)
    winner_tier_after: Mapped[str] = mapped_column(String(8), nullable=False)
    loser_tier_after: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoleDefinition(Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(16), primary_key=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False)


class TitleDefinition(Base):
    __tablename__ = "titles"

    name: Mapped[str] = mapped_column(String(24), primary_key=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False)


class Admin(Base):
    __tablename__ = "admins"

    username: Mapped[str] = mapped_column(String(64), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    admin_username: Mapped[str] = mapped_column(ForeignKey("admins.username", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AdminLoginAttempt(Base):
    __tablename__ = "admin_login_attempts"
    __table_args__ = (Index("ix_admin_login_attempts_ip_created", "ip_hash", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminLog(Base):
    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_username: Mapped[str] = mapped_column(ForeignKey("admins.username"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
