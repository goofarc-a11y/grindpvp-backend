from app.ranking import KIT_IDS, overall_tier, points_for_tier, tier_above, tier_below


def test_kit_catalog_has_fourteen_independent_ranked_kits() -> None:
    assert len(KIT_IDS) == 14
    assert len(set(KIT_IDS)) == 14


def test_tier_points_match_the_rank_table() -> None:
    assert [points_for_tier(tier) for tier in ("HT1", "LT1", "HT2", "LT2", "HT3", "LT3", "HT4", "LT4", "HT5", "LT5", "Unranked")] == [
        60, 45, 30, 20, 10, 6, 4, 3, 2, 1, 0
    ]


def test_overall_uses_exact_midpoints_and_breaks_ties_toward_higher_tier() -> None:
    assert overall_tier(0) == ("Unranked", 0.0)
    assert overall_tier(14) == ("LT5", 1.0)
    assert overall_tier(35) == ("LT4", 2.5)
    assert overall_tier(49)[0] == "HT4"
    assert overall_tier(60)[0] == "HT4"
    assert overall_tier(840) == ("HT1", 60.0)


def test_tier_boundaries_do_not_go_past_the_lowest_or_highest_tier() -> None:
    assert tier_above("HT1") == "HT1"
    assert tier_below("LT5") == "LT5"
