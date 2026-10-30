from uuid import UUID, uuid4


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
        json={"username": "test-admin", "password": "test-password-long"},
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
    assert client.post("/admin/login", json={"username": "test-admin", "password": "wrong"}).status_code == 401


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
