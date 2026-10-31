from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException


def register(client, name: str) -> str:
    player_uuid = str(uuid4())
    response = client.post(
        "/admin/players",
        headers=admin_headers(login(client)),
        json={"uuid": player_uuid, "username": name},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["kits"]) == 14
    return player_uuid


def login(client) -> str:
    response = client.post(
        "/admin/login",
        json={"password": "1302"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def admin_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def set_tier(client, token: str, player_uuid: str, kit: str, tier: str) -> None:
    response = client.post(
        "/admin/tiers",
        headers=admin_headers(token),
        json={"uuid": player_uuid, "kit": kit, "tier": tier},
    )
    assert response.status_code == 200, response.text


def submit_match(client, token: str, key: str, kit: str, winner: str, loser: str):
    return client.post(
        "/admin/matches",
        headers=admin_headers(token),
        json={
            "idempotency_key": key,
            "kit": kit,
            "winner_uuid": winner,
            "loser_uuid": loser,
        },
    )


def test_registration_profiles_and_public_leaderboards(client) -> None:
    first = register(client, "PlayerOne")
    second = register(client, "PlayerTwo")
    token = login(client)

    verified = client.post(
        "/admin/verify",
        headers=admin_headers(token),
        json={"uuid": first, "verified": True},
    )
    assert verified.status_code == 200
    assert verified.json()["title_name"] == "Member"

    page = client.get("/leaderboard/sword?page=1&page_size=1")
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["uuid"] == first
    assert client.get("/leaderboard/overall").json()["total"] == 1
    assert client.get(f"/profiles/{second}").json()["verified"] is False
    assert len(client.get(f"/players/{first}/stats").json()["kits"]) == 14


def test_clients_cannot_submit_matches_and_admin_session_can_be_revoked(client) -> None:
    response = client.post("/matches", json={})
    assert response.status_code == 403

    token = login(client)
    logout = client.post("/admin/logout", headers=admin_headers(token))
    assert logout.status_code == 204
    protected = client.get("/admin/logs", headers=admin_headers(token))
    assert protected.status_code == 401


def test_match_is_idempotent_updates_stats_and_rejects_reused_keys(client) -> None:
    winner = register(client, "RankedWinner")
    loser = register(client, "RankedLoser")
    token = login(client)
    set_tier(client, token, winner, "sword", "LT3")
    set_tier(client, token, loser, "sword", "HT3")

    first = submit_match(client, token, "match:ranked:0001", "sword", winner, loser)
    duplicate = submit_match(client, token, "match:ranked:0001", "sword", winner, loser)
    assert first.status_code == duplicate.status_code == 200
    assert first.json()["id"] == duplicate.json()["id"]
    assert first.json()["winner_tier_after"] == "HT3"

    conflict = submit_match(client, token, "match:ranked:0001", "sword", loser, winner)
    assert conflict.status_code == 409
    stats = client.get(f"/profiles/{winner}").json()
    sword = next(item for item in stats["kits"] if item["kit"] == "sword")
    assert sword["wins"] == 1
    assert sword["tier"] == "HT3"
    history = client.get(f"/matches/{winner}").json()
    assert history["total"] == 1


def test_two_consecutive_losses_derank_but_a_win_resets_the_streak(client) -> None:
    player = register(client, "DerankPlayer")
    opponent = register(client, "DerankOpponent")
    third = register(client, "DerankThird")
    token = login(client)
    set_tier(client, token, player, "axe", "HT3")
    set_tier(client, token, opponent, "axe", "HT3")
    set_tier(client, token, third, "axe", "HT3")

    assert submit_match(client, token, "derank:one:0001", "axe", opponent, player).status_code == 200
    set_tier(client, token, third, "axe", "HT3")
    assert submit_match(client, token, "derank:win:0001", "axe", player, third).status_code == 200
    assert submit_match(client, token, "derank:two:0001", "axe", opponent, player).status_code == 200
    before_second_loss = client.get(f"/profiles/{player}").json()
    assert next(item for item in before_second_loss["kits"] if item["kit"] == "axe")["tier"] == "HT3"
    set_tier(client, token, third, "axe", "HT3")
    assert submit_match(client, token, "derank:three:0001", "axe", third, player).status_code == 200
    after_second_loss = client.get(f"/profiles/{player}").json()
    assert next(item for item in after_second_loss["kits"] if item["kit"] == "axe")["tier"] == "LT3"


def test_ht1_challenge_and_single_holder_invariant(client) -> None:
    challenger = register(client, "TierChallenger")
    first = register(client, "TierOneA")
    second = register(client, "TierOneB")
    token = login(client)
    for player in (challenger, first, second):
        set_tier(client, token, player, "uhc", "LT1")
        client.post(
            "/admin/verify",
            headers=admin_headers(token),
            json={"uuid": player, "verified": True},
        )

    first_match = submit_match(client, token, "ht1:challenge:001", "uhc", challenger, first)
    assert first_match.status_code == 200
    assert first_match.json()["winner_tier_after"] == "LT1"
    second_match = submit_match(client, token, "ht1:challenge:002", "uhc", challenger, second)
    assert second_match.status_code == 200
    assert second_match.json()["winner_tier_after"] == "HT1"

    replacement = register(client, "NewTierOne")
    client.post(
        "/admin/verify",
        headers=admin_headers(token),
        json={"uuid": replacement, "verified": True},
    )
    set_tier(client, token, replacement, "uhc", "LT2")
    takeover = submit_match(client, token, "ht1:takeover:001", "uhc", replacement, challenger)
    assert takeover.status_code == 200
    assert takeover.json()["winner_tier_after"] == "HT1"
    assert takeover.json()["loser_tier_after"] == "LT1"
    entries = client.get("/leaderboard/uhc").json()["items"]
    assert sum(entry["tier"] == "HT1" for entry in entries) == 1


def test_two_equal_tier_wins_promote_and_derank_never_falls_below_lt5(client) -> None:
    winner = register(client, "EqualTierWinner")
    opponent = register(client, "EqualOpponent")
    weakest = register(client, "WeakestRanked")
    token = login(client)
    set_tier(client, token, winner, "mace", "LT3")
    set_tier(client, token, opponent, "mace", "LT3")
    first = submit_match(client, token, "equal:tier:0001", "mace", winner, opponent)
    second = submit_match(client, token, "equal:tier:0002", "mace", winner, opponent)
    assert first.status_code == second.status_code == 200
    assert second.json()["winner_tier_after"] == "HT3"

    set_tier(client, token, weakest, "mace", "LT5")
    assert submit_match(client, token, "minimum:tier:001", "mace", weakest, winner).status_code == 200
    after_one_loss = client.get(f"/profiles/{winner}").json()
    assert next(item for item in after_one_loss["kits"] if item["kit"] == "mace")["tier"] == "HT3"

    set_tier(client, token, winner, "mace", "LT5")
    set_tier(client, token, weakest, "mace", "Unranked")
    assert submit_match(client, token, "minimum:tier:002", "mace", weakest, winner).status_code == 200
    assert submit_match(client, token, "minimum:tier:003", "mace", weakest, winner).status_code == 200
    after_derank = client.get(f"/profiles/{winner}").json()
    assert next(item for item in after_derank["kits"] if item["kit"] == "mace")["tier"] == "LT5"


def test_admin_roles_titles_and_audit_log(client) -> None:
    player = register(client, "ManagedPlayer")
    token = login(client)
    headers = admin_headers(token)
    assert client.post("/admin/titles", headers=headers, json={"uuid": player, "title": "Cup Winner"}).status_code == 409
    assert client.post("/admin/verify", headers=headers, json={"uuid": player, "verified": True}).status_code == 200
    title = client.post("/admin/titles", headers=headers, json={"uuid": player, "title": "Cup Winner"})
    assert title.status_code == 200
    assert title.json()["title_name"] == "Cup Winner"
    role = client.post("/admin/roles", headers=headers, json={"uuid": player, "role": "Admin"})
    assert role.status_code == 200
    assert role.json()["role_name"] == "Admin"
    logs = client.get("/admin/logs", headers=headers)
    assert logs.status_code == 200
    assert logs.json()["total"] >= 3


def test_invalid_kit_uuid_and_admin_credentials_are_rejected(client) -> None:
    assert client.get("/leaderboard/unknown").status_code == 404
    assert client.get(f"/profiles/{UUID(int=0)}").status_code == 404
    assert client.post("/admin/login", json={"password": "wrong"}).status_code == 401


def test_admin_login_with_configured_code_returns_usable_session(client) -> None:
    response = client.post("/admin/login", json={"password": "1302"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert "password" not in body
    assert "username" not in body
    assert client.get(
        "/admin/logs",
        headers=admin_headers(body["access_token"]),
    ).status_code == 200


def test_admin_login_rate_limit_is_enforced(client) -> None:
    for _ in range(5):
        assert client.post("/admin/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/admin/login", json={"password": "1302"}).status_code == 429


def test_untrusted_uuid_registration_is_rejected_and_admin_verifies_by_name(client) -> None:
    player_uuid = str(uuid4())
    public = client.post("/players", json={"uuid": player_uuid, "username": "ClaimedPlayer"})
    assert public.status_code == 403

    token = login(client)
    created = client.post(
        "/admin/players",
        headers=admin_headers(token),
        json={"uuid": player_uuid, "username": "ClaimedPlayer"},
    )
    assert created.status_code == 200
    verified = client.post(
        "/admin/verify",
        headers=admin_headers(token),
        json={"username": "claimedplayer", "verified": True},
    )
    assert verified.status_code == 200
    assert verified.json()["verified"] is True


def test_admin_can_register_and_manage_player_by_username(client, monkeypatch) -> None:
    from app import routes

    player_uuid = str(uuid4())
    monkeypatch.setattr(
        routes,
        "resolve_minecraft_username",
        lambda username: (player_uuid, "NameOnlyPlayer"),
    )
    token = login(client)
    headers = admin_headers(token)

    created = client.post(
        "/admin/players",
        headers=headers,
        json={"username": "NameOnlyPlayer"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["uuid"] == player_uuid

    verified = client.post(
        "/admin/verify",
        headers=headers,
        json={"username": "nameonlyplayer", "verified": True},
    )
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    refreshed = client.post(
        "/admin/players",
        headers=headers,
        json={"username": "NameOnlyPlayer"},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["verified"] is True

    role = client.post(
        "/admin/roles",
        headers=headers,
        json={"username": "NameOnlyPlayer", "role": "Admin"},
    )
    assert role.status_code == 200
    assert role.json()["role_name"] == "Admin"

    title = client.post(
        "/admin/titles",
        headers=headers,
        json={"username": "NameOnlyPlayer", "title": "Cup Winner"},
    )
    assert title.status_code == 200
    assert title.json()["title_name"] == "Cup Winner"

    tier = client.post(
        "/admin/tiers",
        headers=headers,
        json={"username": "NameOnlyPlayer", "kit": "sword", "tier": "HT1"},
    )
    assert tier.status_code == 200
    stats = client.post(
        "/admin/stats",
        headers=headers,
        json={"username": "NameOnlyPlayer", "kit": "sword", "wins": 3, "losses": 1},
    )
    assert stats.status_code == 200
    assert next(kit for kit in stats.json()["kits"] if kit["kit"] == "sword")["wins"] == 3

    presentation = client.get("/players/presentation")
    assert presentation.status_code == 200
    item = presentation.json()["items"][0]
    assert item["uuid"] == player_uuid
    assert item["role_color"] == "#FF7A24"
    assert item["title_color"] == "#f1c40f"
    assert "overall_tier_color" in item


def test_admin_match_can_use_playernames(client) -> None:
    winner = register(client, "NameWinner")
    loser = register(client, "NameLoser")
    token = login(client)
    headers = admin_headers(token)
    for username in ("NameWinner", "NameLoser"):
        verified = client.post(
            "/admin/verify",
            headers=headers,
            json={"username": username, "verified": True},
        )
        assert verified.status_code == 200
    for username, tier in (("NameWinner", "LT3"), ("NameLoser", "HT3")):
        ranked = client.post(
            "/admin/tiers",
            headers=headers,
            json={"username": username, "kit": "sword", "tier": tier},
        )
        assert ranked.status_code == 200

    response = client.post(
        "/admin/matches",
        headers=headers,
        json={
            "idempotency_key": "admin:names-only-match",
            "kit": "sword",
            "winner_username": "namewinner",
            "loser_username": "NameLoser",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["winner_uuid"] == winner
    assert response.json()["loser_uuid"] == loser

    winner_profile = client.get(f"/profiles/{winner}").json()
    loser_profile = client.get(f"/profiles/{loser}").json()
    winner_sword = next(kit for kit in winner_profile["kits"] if kit["kit"] == "sword")
    loser_sword = next(kit for kit in loser_profile["kits"] if kit["kit"] == "sword")
    assert winner_sword == {
        "kit": "sword",
        "tier": "HT3",
        "points": 10,
        "wins": 1,
        "losses": 0,
        "matches": 1,
        "winrate": 100.0,
    }
    assert loser_sword["wins"] == 0
    assert loser_sword["losses"] == loser_sword["matches"] == 1

    kit_board = client.get("/leaderboard/sword").json()
    winner_entry = next(item for item in kit_board["items"] if item["uuid"] == winner)
    assert winner_entry["points"] == winner_sword["points"]
    assert winner_entry["wins"] == winner_sword["wins"]
    overall_board = client.get("/leaderboard/overall").json()
    winner_overall = next(item for item in overall_board["items"] if item["uuid"] == winner)
    assert winner_overall["average_points"] == winner_profile["overall_average_points"]
    assert winner_overall["tier"] == winner_profile["overall_tier"] == "LT5"

    history = client.get(f"/matches/{winner}").json()
    assert history["total"] == 1
    assert history["items"][0]["winner_uuid"] == winner


def test_minecraft_profile_lookup_reports_missing_names(monkeypatch) -> None:
    from app import minecraft_profiles

    class EmptyProfileResponse:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b""

    monkeypatch.setattr(minecraft_profiles, "urlopen", lambda *_args, **_kwargs: EmptyProfileResponse())
    with pytest.raises(HTTPException) as error:
        minecraft_profiles.resolve_minecraft_username("NoSuchPlayer")
    assert error.value.status_code == 404
