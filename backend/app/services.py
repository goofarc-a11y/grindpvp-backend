from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, func, select, update
from sqlalchemy.orm import Session

from app.models import (
    AdminLog,
    KitLock,
    Match,
    Player,
    PlayerKit,
    RoleDefinition,
    TitleDefinition,
)
from app.ranking import KIT_IDS, TIER_POINTS, apply_match_result, overall_tier, points_for_tier
from app.schemas import KitStatsOut, MatchCreate


def canonical_uuid(value: UUID | str) -> str:
    return str(value).lower()


def get_player_or_404(session: Session, player_uuid: UUID | str) -> Player:
    player = session.get(Player, canonical_uuid(player_uuid))
    if player is None:
        raise HTTPException(status_code=404, detail="Player was not found.")
    return player


def get_player_by_username_or_404(session: Session, username: str) -> Player:
    player = session.scalar(select(Player).where(func.lower(Player.username) == username.lower()))
    if player is None:
        raise HTTPException(status_code=404, detail="Player was not found.")
    return player


def ensure_player_kits(session: Session, player: Player) -> dict[str, PlayerKit]:
    existing = {record.kit: record for record in player.kits}
    for kit in KIT_IDS:
        if kit not in existing:
            record = PlayerKit(player_uuid=player.uuid, kit=kit)
            session.add(record)
            existing[kit] = record
    session.flush()
    return existing


def player_stats(session: Session, player: Player) -> tuple[list[KitStatsOut], str, float]:
    kits = ensure_player_kits(session, player)
    stats: list[KitStatsOut] = []
    total_points = 0
    for kit in KIT_IDS:
        record = kits[kit]
        points = points_for_tier(record.tier)
        total_points += points
        matches = record.wins + record.losses
        stats.append(
            KitStatsOut(
                kit=kit,
                tier=record.tier,
                points=points,
                wins=record.wins,
                losses=record.losses,
                matches=matches,
                winrate=round(record.wins / matches * 100, 2) if matches else 0.0,
            )
        )
    tier, average = overall_tier(total_points, len(KIT_IDS))
    return stats, tier, average


def player_payload(session: Session, player: Player) -> dict[str, object]:
    stats, tier, average = player_stats(session, player)
    return {
        "uuid": player.uuid,
        "username": player.username,
        "verified": player.verified,
        "role_name": player.role_name,
        "title_name": player.title_name,
        "overall_tier": tier,
        "overall_average_points": round(average, 2),
        "kits": stats,
    }


def write_admin_log(
    session: Session,
    admin_username: str,
    action: str,
    target_uuid: str | None,
    details: dict[str, object],
) -> None:
    session.add(
        AdminLog(
            admin_username=admin_username,
            action=action,
            target_uuid=target_uuid,
            details=details,
        )
    )


def submit_match(session: Session, payload: MatchCreate, admin_username: str) -> Match:
    winner_uuid = canonical_uuid(payload.winner_uuid)
    loser_uuid = canonical_uuid(payload.loser_uuid)
    kit = payload.kit
    if winner_uuid == loser_uuid:
        raise HTTPException(status_code=422, detail="A player cannot play against themselves.")

    with session.begin_nested():
        # Updating the kit's lock row serializes all match and HT1 updates for this kit.
        lock_result = session.execute(
            update(KitLock).where(KitLock.kit == kit).values(kit=kit)
        )
        if lock_result.rowcount != 1:
            raise HTTPException(status_code=500, detail="Ranked kit has not been initialized.")

        existing = session.scalar(
            select(Match).where(Match.idempotency_key == payload.idempotency_key)
        )
        if existing is not None:
            if (
                existing.kit != kit
                or existing.winner_uuid != winner_uuid
                or existing.loser_uuid != loser_uuid
            ):
                raise HTTPException(status_code=409, detail="Idempotency key was already used for a different match.")
            return existing

        winner = session.scalar(select(Player).where(Player.uuid == winner_uuid).with_for_update())
        loser = session.scalar(select(Player).where(Player.uuid == loser_uuid).with_for_update())
        if winner is None or loser is None:
            raise HTTPException(status_code=404, detail="Both match players must be registered.")

        winner_kit = session.get(PlayerKit, (winner_uuid, kit))
        loser_kit = session.get(PlayerKit, (loser_uuid, kit))
        if winner_kit is None:
            winner_kit = PlayerKit(player_uuid=winner_uuid, kit=kit)
            session.add(winner_kit)
        if loser_kit is None:
            loser_kit = PlayerKit(player_uuid=loser_uuid, kit=kit)
            session.add(loser_kit)
        session.flush()

        loser_tier_before = loser_kit.tier
        if loser_tier_before == "HT1":
            # Demote the incumbent before assigning HT1 to the challenger.
            loser_kit.tier = "LT1"
            session.flush()

        lt1_uuids = set(
            session.scalars(
                select(PlayerKit.player_uuid).where(PlayerKit.kit == kit, PlayerKit.tier == "LT1")
            ).all()
        )
        has_ht1 = session.scalar(
            select(PlayerKit.player_uuid)
            .where(PlayerKit.kit == kit, PlayerKit.tier == "HT1")
            .limit(1)
        ) is not None
        winner_before, loser_before = apply_match_result(
            winner_kit,
            loser_kit,
            lt1_uuids,
            has_ht1,
            loser_tier_before,
        )
        match = Match(
            idempotency_key=payload.idempotency_key,
            kit=kit,
            winner_uuid=winner_uuid,
            loser_uuid=loser_uuid,
            winner_tier_before=winner_before,
            loser_tier_before=loser_before,
            winner_tier_after=winner_kit.tier,
            loser_tier_after=loser_kit.tier,
        )
        session.add(match)
        write_admin_log(
            session,
            admin_username,
            "match.submitted",
            winner_uuid,
            {
                "match_key": payload.idempotency_key,
                "kit": kit,
                "winner_uuid": winner_uuid,
                "loser_uuid": loser_uuid,
            },
        )
        session.flush()
        return match


def leaderboard_page(
    session: Session,
    kit: str,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, object]], int]:
    total = session.scalar(select(func.count()).select_from(Player).where(Player.verified.is_(True))) or 0
    offset = (page - 1) * page_size
    points = case(*[(PlayerKit.tier == tier, value) for tier, value in TIER_POINTS.items()], else_=0)
    rows = session.execute(
        select(Player, PlayerKit, points.label("points"))
        .outerjoin(
            PlayerKit,
            and_(PlayerKit.player_uuid == Player.uuid, PlayerKit.kit == kit),
        )
        .where(Player.verified.is_(True))
        .order_by(
            points.desc(),
            func.coalesce(PlayerKit.wins, 0).desc(),
            Player.username.collate("NOCASE"),
        )
        .offset(offset)
        .limit(page_size)
    ).all()
    entries: list[dict[str, object]] = []
    for rank, (player, record, tier_points) in enumerate(rows, start=offset + 1):
        tier = record.tier if record else "Unranked"
        wins = record.wins if record else 0
        losses = record.losses if record else 0
        matches = wins + losses
        entries.append(
            {
                "uuid": player.uuid,
                "username": player.username,
                "role_name": player.role_name,
                "title_name": player.title_name,
                "tier": tier,
                "points": tier_points,
                "wins": wins,
                "losses": losses,
                "matches": matches,
                "winrate": round(wins / matches * 100, 2) if matches else 0.0,
                "rank": rank,
            }
        )
    return entries, total


def overall_leaderboard_page(
    session: Session,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, object]], int]:
    total = session.scalar(select(func.count()).select_from(Player).where(Player.verified.is_(True))) or 0
    offset = (page - 1) * page_size
    points_per_kit = case(*[(PlayerKit.tier == tier, value) for tier, value in TIER_POINTS.items()], else_=0)
    total_points = func.coalesce(func.sum(points_per_kit), 0)
    rows = session.execute(
        select(Player, total_points.label("total_points"))
        .outerjoin(PlayerKit, PlayerKit.player_uuid == Player.uuid)
        .where(Player.verified.is_(True))
        .group_by(Player.uuid)
        .order_by(total_points.desc(), Player.username.collate("NOCASE"))
        .offset(offset)
        .limit(page_size)
    ).all()
    entries: list[dict[str, object]] = []
    for rank, (player, point_total) in enumerate(rows, start=offset + 1):
        tier, average = overall_tier(int(point_total))
        entries.append(
            {
                "uuid": player.uuid,
                "username": player.username,
                "role_name": player.role_name,
                "title_name": player.title_name,
                "tier": tier,
                "average_points": round(average, 2),
                "rank": rank,
            }
        )
    return entries, total
