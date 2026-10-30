import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models import (
    Admin,
    AdminLoginAttempt,
    AdminLog,
    KitLock,
    Match,
    Player,
    PlayerKit,
    RoleDefinition,
    TitleDefinition,
)
from app.ranking import KIT_IDS, ROLE_COLORS, TIERS, TIER_POINTS, TITLE_COLORS, overall_tier, points_for_tier
from app.minecraft_profiles import resolve_minecraft_username
from app.schemas import (
    AdminMatchCreate,
    AdminLogPage,
    AdminLogin,
    AdminPlayerCreate,
    AdminToken,
    CatalogOut,
    LeaderboardPage,
    MatchCreate,
    MatchOut,
    MatchPage,
    OverallLeaderboardPage,
    PlayerCreate,
    PlayerOut,
    PlayerPage,
    PlayerPresentation,
    PlayerPresentationPage,
    PlayerStatsUpdate,
    RoleUpdate,
    TierUpdate,
    TitleUpdate,
    VerificationUpdate,
)
from app.security import create_admin_session, require_admin, revoke_session, verify_password
from app.services import (
    canonical_uuid,
    get_player_by_username_or_404,
    get_player_or_404,
    leaderboard_page,
    overall_leaderboard_page,
    player_payload,
    submit_match,
    write_admin_log,
)

public_router = APIRouter()
admin_router = APIRouter(prefix="/admin", tags=["admin"])
_bearer_auth = HTTPBearer()


def get_player_by_username_or_404_optional(session: Session, username: str) -> Player | None:
    return session.scalar(select(Player).where(func.lower(Player.username) == username.lower()))


def _player_from_identifier(session: Session, player_uuid: UUID | None, username: str | None) -> Player:
    if player_uuid is not None:
        return get_player_or_404(session, player_uuid)
    if username is None:
        raise HTTPException(status_code=422, detail="A Minecraft username is required.")
    return get_player_by_username_or_404(session, username)


@public_router.get("/catalog", response_model=CatalogOut, tags=["catalog"])
def get_catalog() -> CatalogOut:
    return CatalogOut(
        kits=list(KIT_IDS),
        tiers=[{"name": tier.name, "points": tier.points, "color": tier.color} for tier in TIERS],
        roles=[{"name": name, "color": color} for name, color in ROLE_COLORS.items()],
        titles=[{"name": name, "color": color} for name, color in TITLE_COLORS.items()],
    )


@public_router.get("/players", response_model=PlayerPage, tags=["players"])
def list_players(
    search: str | None = Query(default=None, min_length=1, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db),
) -> PlayerPage:
    filters = [Player.verified.is_(True)]
    if search:
        filters.append(Player.username.ilike(f"%{search}%"))
    total = session.scalar(select(func.count()).select_from(Player).where(*filters)) or 0
    players = session.scalars(
        select(Player)
        .options(selectinload(Player.kits))
        .where(*filters)
        .order_by(Player.username)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return PlayerPage(
        items=[player_payload(session, player) for player in players],
        page=page,
        page_size=page_size,
        total=total,
    )


@public_router.get("/players/presentation", response_model=PlayerPresentationPage, tags=["players"])
def list_player_presentations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=1000, ge=1, le=5000),
    session: Session = Depends(get_db),
) -> PlayerPresentationPage:
    players = session.scalars(
        select(Player)
        .options(selectinload(Player.kits))
        .where(Player.verified.is_(True))
        .order_by(Player.username)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    tier_colors = {tier.name: tier.color for tier in TIERS}
    items = []
    for player in players:
        total_points = sum(TIER_POINTS[record.tier] for record in player.kits)
        tier, _ = overall_tier(total_points)
        items.append(
            PlayerPresentation(
                uuid=player.uuid,
                username=player.username,
                role_name=player.role_name,
                role_color=ROLE_COLORS.get(player.role_name),
                title_name=player.title_name,
                title_color=TITLE_COLORS.get(player.title_name),
                overall_tier=tier,
                overall_tier_color=tier_colors[tier],
            )
        )
    return PlayerPresentationPage(items=items)


@public_router.post("/players", status_code=status.HTTP_403_FORBIDDEN, tags=["players"])
def reject_unverified_player_registration(payload: PlayerCreate) -> None:
    del payload
    raise HTTPException(
        status_code=403,
        detail="Player registration requires a trusted Minecraft account-ownership flow. Ask an administrator to add the player.",
    )


@public_router.get("/players/{player_uuid}/stats", response_model=PlayerOut, tags=["players"])
def get_player_stats(player_uuid: UUID, session: Session = Depends(get_db)) -> PlayerOut:
    return player_payload(session, get_player_or_404(session, player_uuid))


@public_router.get("/profiles/{player_uuid}", response_model=PlayerOut, tags=["profiles"])
def get_profile(player_uuid: UUID, session: Session = Depends(get_db)) -> PlayerOut:
    return player_payload(session, get_player_or_404(session, player_uuid))


@public_router.get("/leaderboard/overall", response_model=OverallLeaderboardPage, tags=["leaderboard"])
def overall_leaderboard(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db),
) -> OverallLeaderboardPage:
    entries, total = overall_leaderboard_page(session, page, page_size)
    return OverallLeaderboardPage(items=entries, page=page, page_size=page_size, total=total)


@public_router.get("/leaderboard/{kit}", response_model=LeaderboardPage, tags=["leaderboard"])
def kit_leaderboard(
    kit: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db),
) -> LeaderboardPage:
    if kit not in KIT_IDS:
        raise HTTPException(status_code=404, detail="Unknown ranked kit.")
    entries, total = leaderboard_page(session, kit, page, page_size)
    return LeaderboardPage(kit=kit, items=entries, page=page, page_size=page_size, total=total)


@public_router.post("/matches", status_code=status.HTTP_403_FORBIDDEN, tags=["matches"])
def reject_client_match_submission() -> None:
    raise HTTPException(
        status_code=403,
        detail="Match results can only be submitted by an authenticated administrator.",
    )


def _match_page(session: Session, player_uuid: str | None, page: int, page_size: int) -> MatchPage:
    filters = []
    if player_uuid is not None:
        filters.append((Match.winner_uuid == player_uuid) | (Match.loser_uuid == player_uuid))
    total = session.scalar(select(func.count()).select_from(Match).where(*filters)) or 0
    matches = session.scalars(
        select(Match)
        .where(*filters)
        .order_by(Match.created_at.desc(), Match.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return MatchPage(items=[MatchOut.model_validate(match) for match in matches], page=page, page_size=page_size, total=total)


@public_router.get("/matches", response_model=MatchPage, tags=["matches"])
def list_matches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db),
) -> MatchPage:
    return _match_page(session, None, page, page_size)


@public_router.get("/matches/{player_uuid}", response_model=MatchPage, tags=["matches"])
def player_match_history(
    player_uuid: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db),
) -> MatchPage:
    get_player_or_404(session, player_uuid)
    return _match_page(session, canonical_uuid(player_uuid), page, page_size)


@admin_router.post("/login", response_model=AdminToken)
def admin_login(
    payload: AdminLogin,
    request: Request,
    session: Session = Depends(get_db),
) -> AdminToken:
    settings = get_settings()
    if not settings.admin_password:
        raise HTTPException(
            status_code=503,
            detail="Admin login is not configured. Set ADMIN_PASSWORD on the backend.",
        )
    client_ip = request.client.host if request.client is not None else "unknown"
    ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)
    session.execute(
        delete(AdminLoginAttempt).where(AdminLoginAttempt.created_at < now - timedelta(days=1))
    )
    recent_failures = session.scalar(
        select(func.count())
        .select_from(AdminLoginAttempt)
        .where(
            AdminLoginAttempt.ip_hash == ip_hash,
            AdminLoginAttempt.created_at >= now - timedelta(minutes=15),
        )
    ) or 0
    daily_failures = session.scalar(
        select(func.count())
        .select_from(AdminLoginAttempt)
        .where(
            AdminLoginAttempt.ip_hash == ip_hash,
            AdminLoginAttempt.created_at >= now - timedelta(days=1),
        )
    ) or 0
    if recent_failures >= 5 or daily_failures >= 10:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    admin = session.get(Admin, settings.admin_username)
    if admin is None or not verify_password(payload.password, admin.password_hash):
        session.add(AdminLoginAttempt(ip_hash=ip_hash))
        session.commit()
        raise HTTPException(status_code=401, detail="Invalid password.")
    token, expires_at = create_admin_session(session, admin)
    write_admin_log(session, admin.username, "admin.login", None, {})
    return AdminToken(access_token=token, expires_at=expires_at)


@admin_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def admin_logout(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_auth),
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> Response:
    revoke_session(session, credentials.credentials, admin_username)
    write_admin_log(session, admin_username, "admin.logout", None, {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post("/players", response_model=PlayerOut)
def admin_create_or_update_player(
    payload: AdminPlayerCreate,
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> PlayerOut:
    if payload.uuid is None:
        existing = get_player_by_username_or_404_optional(session, payload.username)
        if existing is None:
            player_uuid, resolved_username = resolve_minecraft_username(payload.username)
        else:
            player_uuid, resolved_username = existing.uuid, existing.username
    else:
        player_uuid, resolved_username = canonical_uuid(payload.uuid), payload.username
    player = session.get(Player, player_uuid)
    created = player is None
    if player is None:
        username_owner = get_player_by_username_or_404_optional(session, resolved_username)
        if username_owner is not None:
            raise HTTPException(status_code=409, detail="This Minecraft username is already registered.")
        player = Player(
            uuid=player_uuid,
            username=resolved_username,
            verified=payload.verified if payload.verified is not None else False,
        )
        session.add(player)
    else:
        username_owner = session.scalar(
            select(Player.uuid).where(
                func.lower(Player.username) == resolved_username.lower(),
                Player.uuid != player_uuid,
            )
        )
        if username_owner is not None:
            raise HTTPException(status_code=409, detail="This Minecraft username is already registered.")
        player.username = resolved_username
        if payload.verified is not None:
            player.verified = payload.verified
    if player.verified and player.title_name is None:
        player.title_name = "Member"
    if not player.verified:
        player.title_name = None
    session.flush()
    write_admin_log(
        session,
        admin_username,
        "player.created" if created else "player.updated",
        player_uuid,
        {"username": resolved_username, "verified": player.verified},
    )
    return player_payload(session, player)


@admin_router.post("/verify", response_model=PlayerOut)
def admin_set_verification(
    payload: VerificationUpdate,
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> PlayerOut:
    player = _player_from_identifier(session, payload.uuid, payload.username)
    player.verified = payload.verified
    if payload.verified and player.title_name is None:
        player.title_name = "Member"
    elif not payload.verified:
        player.title_name = None
    write_admin_log(
        session,
        admin_username,
        "player.verification_changed",
        player.uuid,
        {"verified": payload.verified},
    )
    return player_payload(session, player)


@admin_router.post("/roles", response_model=PlayerOut)
def admin_set_role(
    payload: RoleUpdate,
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> PlayerOut:
    player = _player_from_identifier(session, payload.uuid, payload.username)
    if payload.role is not None and session.get(RoleDefinition, payload.role) is None:
        raise HTTPException(status_code=422, detail="Unknown role.")
    previous_role = player.role_name
    player.role_name = payload.role
    write_admin_log(
        session,
        admin_username,
        "player.role_changed",
        player.uuid,
        {"from": previous_role, "to": payload.role},
    )
    return player_payload(session, player)


@admin_router.post("/titles", response_model=PlayerOut)
def admin_set_title(
    payload: TitleUpdate,
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> PlayerOut:
    player = _player_from_identifier(session, payload.uuid, payload.username)
    if payload.title is not None:
        if not player.verified:
            raise HTTPException(status_code=409, detail="Only verified players can receive a title.")
        if session.get(TitleDefinition, payload.title) is None:
            raise HTTPException(status_code=422, detail="Unknown title.")
    previous_title = player.title_name
    player.title_name = payload.title
    write_admin_log(
        session,
        admin_username,
        "player.title_changed",
        player.uuid,
        {"from": previous_title, "to": payload.title},
    )
    return player_payload(session, player)


@admin_router.post("/matches", response_model=MatchOut)
def admin_submit_match(
    payload: AdminMatchCreate,
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> MatchOut:
    winner = (
        get_player_by_username_or_404(session, payload.winner_username)
        if payload.winner_username is not None
        else get_player_or_404(session, payload.winner_uuid)
    )
    loser = (
        get_player_by_username_or_404(session, payload.loser_username)
        if payload.loser_username is not None
        else get_player_or_404(session, payload.loser_uuid)
    )
    match = submit_match(
        session,
        MatchCreate(
            idempotency_key=payload.idempotency_key,
            kit=payload.kit,
            winner_uuid=winner.uuid,
            loser_uuid=loser.uuid,
        ),
        admin_username,
    )
    return MatchOut.model_validate(match)


@admin_router.post("/tiers", response_model=PlayerOut)
def admin_set_tier(
    payload: TierUpdate,
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> PlayerOut:
    player = _player_from_identifier(session, payload.uuid, payload.username)
    target_tier = payload.tier or "Unranked"
    lock_result = session.execute(
        update(KitLock).where(KitLock.kit == payload.kit).values(kit=payload.kit)
    )
    if lock_result.rowcount != 1:
        raise HTTPException(status_code=500, detail="Ranked kit has not been initialized.")
    record = session.get(PlayerKit, (player.uuid, payload.kit))
    if record is None:
        record = PlayerKit(player_uuid=player.uuid, kit=payload.kit)
        session.add(record)
    previous_tier = record.tier
    displaced_uuid: str | None = None
    if target_tier == "HT1":
        current_holder = session.scalar(
            select(PlayerKit).where(
                PlayerKit.kit == payload.kit,
                PlayerKit.tier == "HT1",
                PlayerKit.player_uuid != player.uuid,
            )
        )
        if current_holder is not None:
            current_holder.tier = "LT1"
            current_holder.loss_streak = 0
            current_holder.equal_tier_wins = 0
            current_holder.ht1_defeated = []
            displaced_uuid = current_holder.player_uuid
            session.flush()
    record.tier = target_tier
    record.loss_streak = 0
    record.equal_tier_wins = 0
    record.ht1_defeated = []
    write_admin_log(
        session,
        admin_username,
        "player.tier_changed",
        player.uuid,
        {
            "kit": payload.kit,
            "from": previous_tier,
            "to": target_tier,
            "displaced_ht1_uuid": displaced_uuid,
        },
    )
    return player_payload(session, player)


@admin_router.post("/stats", response_model=PlayerOut)
def admin_correct_stats(
    payload: PlayerStatsUpdate,
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> PlayerOut:
    player = _player_from_identifier(session, payload.uuid, payload.username)
    record = session.get(PlayerKit, (player.uuid, payload.kit))
    if record is None:
        record = PlayerKit(player_uuid=player.uuid, kit=payload.kit)
        session.add(record)
    previous = {"wins": record.wins, "losses": record.losses}
    record.wins = payload.wins
    record.losses = payload.losses
    record.loss_streak = 0
    write_admin_log(
        session,
        admin_username,
        "player.stats_corrected",
        player.uuid,
        {"kit": payload.kit, "from": previous, "to": {"wins": payload.wins, "losses": payload.losses}},
    )
    return player_payload(session, player)


@admin_router.get("/matches", response_model=MatchPage)
def admin_list_matches(
    player_uuid: UUID | None = None,
    username: str | None = Query(default=None, min_length=3, max_length=16, pattern=r"^[A-Za-z0-9_]+$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> MatchPage:
    del admin_username
    if player_uuid is not None and username is not None:
        raise HTTPException(status_code=422, detail="Provide either player_uuid or username, not both.")
    if username is not None:
        player = get_player_by_username_or_404(session, username)
        player_uuid = UUID(player.uuid)
    return _match_page(session, canonical_uuid(player_uuid) if player_uuid else None, page, page_size)


@admin_router.get("/logs", response_model=AdminLogPage)
def admin_list_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> AdminLogPage:
    del admin_username
    total = session.scalar(select(func.count()).select_from(AdminLog)) or 0
    logs = session.scalars(
        select(AdminLog)
        .order_by(AdminLog.created_at.desc(), AdminLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AdminLogPage(
        items=logs,
        page=page,
        page_size=page_size,
        total=total,
    )


@admin_router.get("/players/{player_uuid}", response_model=PlayerOut)
def admin_get_player(
    player_uuid: UUID,
    admin_username: str = Depends(require_admin),
    session: Session = Depends(get_db),
) -> PlayerOut:
    del admin_username
    return player_payload(session, get_player_or_404(session, player_uuid))
