from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

KitId = Literal[
    "sword",
    "axe",
    "uhc",
    "diapot",
    "nethop",
    "smp",
    "mace",
    "crystal",
    "speed",
    "diasmp",
    "ogvanilla",
    "cart",
    "spearmace",
    "manhunt",
]
TierId = Literal["HT1", "LT1", "HT2", "LT2", "HT3", "LT3", "HT4", "LT4", "HT5", "LT5", "Unranked"]
Username = Annotated[str, StringConstraints(min_length=3, max_length=16, pattern=r"^[A-Za-z0-9_]+$")]
UuidValue = UUID
IdempotencyKey = Annotated[str, StringConstraints(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")]


class PlayerCreate(BaseModel):
    uuid: UuidValue
    username: Username


class AdminPlayerCreate(BaseModel):
    uuid: UuidValue | None = None
    username: Username
    verified: bool | None = None


class KitStatsOut(BaseModel):
    kit: KitId
    tier: TierId
    points: int
    wins: int
    losses: int
    matches: int
    winrate: float


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: str
    username: str
    verified: bool
    role_name: str | None
    title_name: str | None
    overall_tier: str
    overall_average_points: float
    kits: list[KitStatsOut]


class PlayerPage(BaseModel):
    items: list[PlayerOut]
    page: int
    page_size: int
    total: int


class MatchCreate(BaseModel):
    idempotency_key: IdempotencyKey
    kit: KitId
    winner_uuid: UuidValue
    loser_uuid: UuidValue


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    idempotency_key: str
    kit: KitId
    winner_uuid: str
    loser_uuid: str
    winner_tier_before: TierId
    loser_tier_before: TierId
    winner_tier_after: TierId
    loser_tier_after: TierId
    created_at: datetime


class MatchPage(BaseModel):
    items: list[MatchOut]
    page: int
    page_size: int
    total: int


class AdminLogin(BaseModel):
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class AdminToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class VerificationUpdate(BaseModel):
    uuid: UuidValue | None = None
    username: Username | None = None
    verified: bool

    @model_validator(mode="after")
    def require_one_player_identifier(self) -> "VerificationUpdate":
        if (self.uuid is None) == (self.username is None):
            raise ValueError("Provide either a Minecraft UUID or an in-game username.")
        return self


class RoleUpdate(BaseModel):
    uuid: UuidValue | None = None
    username: Username | None = None
    role: Annotated[str, StringConstraints(min_length=1, max_length=16)] | None

    @model_validator(mode="after")
    def require_one_player_identifier(self) -> "RoleUpdate":
        if (self.uuid is None) == (self.username is None):
            raise ValueError("Provide either a Minecraft UUID or an in-game username.")
        return self


class TitleUpdate(BaseModel):
    uuid: UuidValue | None = None
    username: Username | None = None
    title: Annotated[str, StringConstraints(min_length=1, max_length=24)] | None

    @model_validator(mode="after")
    def require_one_player_identifier(self) -> "TitleUpdate":
        if (self.uuid is None) == (self.username is None):
            raise ValueError("Provide either a Minecraft UUID or an in-game username.")
        return self


class TierUpdate(BaseModel):
    uuid: UuidValue | None = None
    username: Username | None = None
    kit: KitId
    tier: TierId | None

    @model_validator(mode="after")
    def require_one_player_identifier(self) -> "TierUpdate":
        if (self.uuid is None) == (self.username is None):
            raise ValueError("Provide either a Minecraft UUID or an in-game username.")
        return self


class AdminMatchCreate(BaseModel):
    idempotency_key: IdempotencyKey
    kit: KitId
    winner_username: Username | None = None
    loser_username: Username | None = None
    winner_uuid: UuidValue | None = None
    loser_uuid: UuidValue | None = None

    @model_validator(mode="after")
    def require_one_identifier_per_player(self) -> "AdminMatchCreate":
        if (self.winner_username is None) == (self.winner_uuid is None):
            raise ValueError("Provide either the winner's Minecraft username or UUID.")
        if (self.loser_username is None) == (self.loser_uuid is None):
            raise ValueError("Provide either the loser's Minecraft username or UUID.")
        return self


class PlayerStatsUpdate(BaseModel):
    uuid: UuidValue | None = None
    username: Username | None = None
    kit: KitId
    wins: int = Field(ge=0, le=1_000_000)
    losses: int = Field(ge=0, le=1_000_000)

    @model_validator(mode="after")
    def require_one_player_identifier(self) -> "PlayerStatsUpdate":
        if (self.uuid is None) == (self.username is None):
            raise ValueError("Provide either a Minecraft UUID or an in-game username.")
        return self


class LeaderboardEntry(BaseModel):
    uuid: str
    username: str
    role_name: str | None
    title_name: str | None
    tier: TierId
    points: int
    wins: int
    losses: int
    matches: int
    winrate: float
    rank: int


class LeaderboardPage(BaseModel):
    kit: KitId | None
    items: list[LeaderboardEntry]
    page: int
    page_size: int
    total: int


class OverallLeaderboardEntry(BaseModel):
    uuid: str
    username: str
    role_name: str | None
    title_name: str | None
    tier: str
    average_points: float
    rank: int


class OverallLeaderboardPage(BaseModel):
    kit: Literal["overall"] = "overall"
    items: list[OverallLeaderboardEntry]
    page: int
    page_size: int
    total: int


class PlayerPresentation(BaseModel):
    uuid: str
    username: str
    role_name: str | None
    role_color: str | None
    title_name: str | None
    title_color: str | None
    overall_tier: str
    overall_tier_color: str


class PlayerPresentationPage(BaseModel):
    items: list[PlayerPresentation]


class AdminLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_username: str
    action: str
    target_uuid: str | None
    details: dict[str, object]
    created_at: datetime


class AdminLogPage(BaseModel):
    items: list[AdminLogOut]
    page: int
    page_size: int
    total: int


class CatalogOut(BaseModel):
    kits: list[str]
    tiers: list[dict[str, object]]
    roles: list[dict[str, str]]
    titles: list[dict[str, str]]
