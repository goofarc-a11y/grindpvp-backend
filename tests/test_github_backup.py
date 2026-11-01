import base64
import json
import urllib.error
from io import BytesIO

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app import database
from app.config import Settings
from app.github_backup import (
    BackupError,
    _decrypt_backup,
    _encrypt_backup,
    _ensure_backup_branch,
    restore_sqlite,
    save_sqlite,
    validate_backup_settings,
)
from app.models import Base, KitLock


def backup_settings() -> Settings:
    return Settings(
        backup_repository="owner/private-backups",
        backup_token="test-token",
        backup_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
    )


def test_encrypted_backup_round_trip() -> None:
    settings = backup_settings()
    _, key = validate_backup_settings(settings)
    database = b"example sqlite database bytes"

    encrypted = _encrypt_backup(database, key)

    assert _decrypt_backup(encrypted, key) == database
    with pytest.raises(BackupError, match="could not be decrypted"):
        _decrypt_backup(encrypted, b"w" * 32)


def test_save_and_restore_sqlite_backup(monkeypatch, tmp_path) -> None:
    backup_file: dict[str, object] = {}

    def fake_request(url, token, method="GET", body=None, accept="application/vnd.github+json"):
        assert token == "test-token"
        if url.endswith("/git/ref/heads/database-backups"):
            return b'{"ref":"refs/heads/database-backups"}'
        if method == "GET":
            if not backup_file:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, BytesIO())
            return json.dumps(
                {
                    "sha": backup_file["sha"],
                    "content": base64.b64encode(backup_file["content"]).decode("ascii"),
                }
            ).encode("utf-8")

        payload = json.loads(body)
        assert payload["branch"] == "database-backups"
        backup_file["content"] = base64.b64decode(payload["content"])
        backup_file["sha"] = str(int(backup_file.get("sha", "0")) + 1)
        return b"{}"

    monkeypatch.setattr("app.github_backup._request", fake_request)
    monkeypatch.setattr("app.github_backup._BACKUP_BRANCHES", set())
    settings = backup_settings()
    source_path = tmp_path / "source.sqlite"
    source_engine = create_engine(f"sqlite:///{source_path}")
    with source_engine.begin() as connection:
        connection.execute(text("CREATE TABLE players (uuid TEXT PRIMARY KEY, username TEXT)"))
        connection.execute(text("CREATE TABLE player_kits (player_uuid TEXT, kit TEXT)"))
        connection.execute(text("CREATE TABLE matches (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text("INSERT INTO players (uuid, username) VALUES ('player-1', 'PlayerOne')")
        )

    save_sqlite(source_engine, settings)

    restored_path = tmp_path / "restored.sqlite"
    restored_engine = create_engine(f"sqlite:///{restored_path}")
    assert restore_sqlite(restored_engine, settings) is True
    with restored_engine.connect() as connection:
        assert connection.execute(text("SELECT username FROM players")).scalar_one() == "PlayerOne"

    source_engine.dispose()
    restored_engine.dispose()


def test_backup_requires_private_repository_configuration() -> None:
    with pytest.raises(BackupError, match="BACKUP_REPOSITORY"):
        validate_backup_settings(Settings())


def test_backup_rejects_invalid_encryption_key() -> None:
    settings = backup_settings().model_copy(update={"backup_encryption_key": "invalid"})

    with pytest.raises(BackupError, match="32 bytes"):
        validate_backup_settings(settings)


def test_backup_branch_is_created_from_default_branch(monkeypatch) -> None:
    requests: list[tuple[str, str, bytes | None]] = []

    def fake_request(url, token, method="GET", body=None, accept="application/vnd.github+json"):
        requests.append((url, method, body))
        if url.endswith("/git/ref/heads/database-backups"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, BytesIO())
        if url.endswith("/repos/owner/private-backups") and method == "GET":
            return b'{"default_branch":"main"}'
        if url.endswith("/git/ref/heads/main"):
            return b'{"object":{"sha":"main-commit"}}'
        if url.endswith("/git/refs") and method == "POST":
            return b'{"ref":"refs/heads/database-backups"}'
        raise AssertionError(f"Unexpected GitHub request: {method} {url}")

    monkeypatch.setattr("app.github_backup._request", fake_request)
    monkeypatch.setattr("app.github_backup._BACKUP_BRANCHES", set())

    _ensure_backup_branch("owner/private-backups", "test-token")

    assert requests[-1][1] == "POST"
    assert json.loads(requests[-1][2]) == {
        "ref": "refs/heads/database-backups",
        "sha": "main-commit",
    }


def test_database_dependency_saves_after_write(monkeypatch, tmp_path) -> None:
    test_engine = create_engine(f"sqlite:///{tmp_path / 'database.sqlite'}")
    Base.metadata.create_all(test_engine)
    test_sessions = sessionmaker(bind=test_engine)
    backups: list[Engine] = []
    monkeypatch.setattr(database, "engine", test_engine)
    monkeypatch.setattr(database, "SessionLocal", test_sessions)
    monkeypatch.setattr(database, "get_settings", backup_settings)
    monkeypatch.setattr(database, "save_sqlite", lambda engine, settings: backups.append(engine))

    dependency = database.get_db()
    session = next(dependency)
    session.add(KitLock(kit="sword"))
    with pytest.raises(StopIteration):
        next(dependency)

    assert backups == [test_engine]
    with test_engine.connect() as connection:
        assert connection.execute(
            text("SELECT kit FROM kit_locks WHERE kit = 'sword'")
        ).scalar_one() == "sword"
    test_engine.dispose()
