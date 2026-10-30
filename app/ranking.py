from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    name: str
    points: int
    color: str


TIERS = (
    Tier("HT1", 60, "#F1C40F"),
    Tier("LT1", 45, "#D4AC0D"),
    Tier("HT2", 30, "#C0C0C0"),
    Tier("LT2", 20, "#AEB6BF"),
    Tier("HT3", 10, "#CD7F32"),
    Tier("LT3", 6, "#B87333"),
    Tier("HT4", 4, "#B3E5FC"),
    Tier("LT4", 3, "#81D4FA"),
    Tier("HT5", 2, "#800000"),
    Tier("LT5", 1, "#5D001E"),
    Tier("Unranked", 0, "#808080"),
)
TIER_POINTS = {tier.name: tier.points for tier in TIERS}
TIER_ORDER = {tier.name: index for index, tier in enumerate(TIERS)}
KIT_IDS = (
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
)
ROLE_COLORS = {
    "VIP": "#AA55FF",
    "Owner": "#FF5555",
    "Admin": "#FF7A24",
    "Mod": "#AAAAAA",
    "Helper": "#55FF55",
}
TITLE_COLORS = {
    "Member": "#9e99da",
    "Cup Winner": "#f1c40f",
    "Cup Master": "#aa5959",
}


def points_for_tier(tier: str) -> int:
    try:
        return TIER_POINTS[tier]
    except KeyError as error:
        raise ValueError(f"Unknown tier: {tier}") from error


def overall_tier(total_points: int, kit_count: int = len(KIT_IDS)) -> tuple[str, float]:
    if kit_count <= 0:
        raise ValueError("kit_count must be positive")

    tier = TIERS[-1].name
    for candidate in TIERS[:-1]:
        next_candidate = TIERS[TIER_ORDER[candidate.name] + 1]
        # Compare against exact midpoints; an exact tie goes to the higher tier.
        if total_points * 2 >= (candidate.points + next_candidate.points) * kit_count:
            tier = candidate.name
            break
    return tier, total_points / kit_count


def tier_above(tier: str) -> str:
    index = TIER_ORDER[tier]
    return TIERS[max(0, index - 1)].name


def tier_below(tier: str) -> str:
    if tier == "LT5":
        return "LT5"
    if tier == "Unranked":
        return "Unranked"
    index = TIER_ORDER[tier]
    return TIERS[min(len(TIERS) - 2, index + 1)].name


def apply_match_result(
    winner,
    loser,
    lt1_uuids: set[str],
    has_ht1: bool,
    loser_tier_before: str | None = None,
) -> tuple[str, str]:
    """Apply one confirmed match to two PlayerKit rows; caller owns the kit lock."""
    winner_before = winner.tier
    loser_before = loser_tier_before or loser.tier
    winner_points = points_for_tier(winner_before)
    loser_points = points_for_tier(loser_before)

    winner.wins += 1
    winner.loss_streak = 0
    loser.losses += 1

    if winner_before == "HT1":
        winner.equal_tier_wins = 0
    elif winner_points > loser_points:
        winner.equal_tier_wins = 0
    elif winner_points < loser_points:
        winner.tier = loser_before
        winner.equal_tier_wins = 0
        winner.ht1_defeated = []
    else:
        winner.equal_tier_wins += 1
        if winner.equal_tier_wins >= 2:
            next_tier = tier_above(winner_before)
            if next_tier != "HT1" or has_ht1:
                winner.tier = next_tier
            winner.equal_tier_wins = 0

    if winner.tier == "LT1" and not has_ht1 and loser_before == "LT1":
        winner.ht1_defeated = sorted(set(winner.ht1_defeated or []) | {loser.player_uuid})
        required_opponents = lt1_uuids - {winner.player_uuid}
        if required_opponents and required_opponents.issubset(set(winner.ht1_defeated)):
            winner.tier = "HT1"
            winner.equal_tier_wins = 0
            winner.ht1_defeated = []

    if loser_before == "HT1":
        winner.tier = "HT1"
        winner.equal_tier_wins = 0
        winner.ht1_defeated = []
        loser.tier = "LT1"
        loser.equal_tier_wins = 0
        loser.ht1_defeated = []

    if loser_before != "Unranked":
        if winner_points <= loser_points:
            loser.loss_streak += 1
            if loser.loss_streak >= 2:
                loser.tier = tier_below(loser_before)
                loser.loss_streak = 0
                loser.equal_tier_wins = 0
                loser.ht1_defeated = []
        else:
            loser.loss_streak = 0
    else:
        loser.loss_streak = 0
    loser.ht1_defeated = []

    return winner_before, loser_before
