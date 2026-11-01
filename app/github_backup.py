import base64
import gzip
import io
import json
import os
import re
import sqlite3
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.engine import Engine


BACKUP_PATH = "backups/grindpvp.sqlite.gz.enc"
BACKUP_BRANCH = "database-backups"
BACKUP_FORMAT = b"grindpvp-sqlite-backup-v1\x00"
MAX_BACKUP_BYTES = 50 * 1024 * 1024
_BACKUP_LOCK = threading.Lock()
_BACKUP_BRANCHES: set[str] = set()


class BackupError(RuntimeError):
    pass


def backup_is_configured(settings) -> bool:
    return bool(
        settings.backup_repository
        and settings.backup_token
        and settings.backup_encryption_key
    )


def validate_backup_settings(settings) -> tuple[str, bytes]:
    repository = (settings.backup_repository or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise BackupError("BACKUP_REPOSITORY must be set to owner/repository.")
    if not settings.backup_token or not settings.backup_token.strip():
        raise BackupError("BACKUP_TOKEN must be set.")
    if not settings.backup_encryption_key:
        raise BackupError("BACKUP_ENCRYPTION_KEY must be set.")

    try:
        encoded_key = settings.backup_encryption_key.encode("ascii")
        key = base64.b64decode(
            encoded_key + b"=" * (-len(encoded_key) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, ValueError) as error:
        raise BackupError("BACKUP_ENCRYPTION_KEY must be a URL-safe base64 key.") from error
    if len(key) != 32:
        raise BackupError("BACKUP_ENCRYPTION_KEY must decode to exactly 32 bytes.")
    return repository, key


def _database_path(engine: Engine) -> Path:
    if not engine.url.drivername.startswith("sqlite") or not engine.url.database:
        raise BackupError("GitHub file backups require a file-backed SQLite database.")
    if engine.url.database == ":memory:":
        raise BackupError("GitHub file backups cannot use an in-memory SQLite database.")
    return Path(engine.url.database).resolve()


def _api_url(repository: str, path: str = BACKUP_PATH) -> str:
    owner, name = repository.split("/", 1)
    safe_owner = urllib.parse.quote(owner, safe="")
    safe_name = urllib.parse.quote(name, safe="")
    safe_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    return f"https://api.github.com/repos/{safe_owner}/{safe_name}/contents/{safe_path}"


def _repository_url(repository: str, suffix: str = "") -> str:
    owner, name = repository.split("/", 1)
    safe_owner = urllib.parse.quote(owner, safe="")
    safe_name = urllib.parse.quote(name, safe="")
    return f"https://api.github.com/repos/{safe_owner}/{safe_name}{suffix}"


def _request(
    url: str,
    token: str,
    method: str = "GET",
    body: bytes | None = None,
    accept: str = "application/vnd.github+json",
) -> bytes:
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "User-Agent": "GrindPvP-Encrypted-Database-Backup",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise
        if error.code in {409, 422}:
            raise
        raise BackupError(f"GitHub backup request failed with HTTP {error.code}.") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise BackupError("GitHub backup request could not reach GitHub.") from error


def _ensure_backup_branch(repository: str, token: str) -> None:
    if repository in _BACKUP_BRANCHES:
        return
    try:
        _request(
            _repository_url(repository, f"/git/ref/heads/{BACKUP_BRANCH}"),
            token,
        )
        _BACKUP_BRANCHES.add(repository)
        return
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise BackupError("GitHub backup branch could not be checked.") from error

    try:
        metadata = json.loads(_request(_repository_url(repository), token))
        default_branch = metadata["default_branch"]
        if not isinstance(default_branch, str) or not default_branch:
            raise ValueError("Missing default branch.")
        default_ref = json.loads(
            _request(
                _repository_url(
                    repository,
                    f"/git/ref/heads/{urllib.parse.quote(default_branch, safe='')}",
                ),
                token,
            )
        )
        commit_sha = default_ref["object"]["sha"]
        if not isinstance(commit_sha, str) or not commit_sha:
            raise ValueError("Missing default branch commit.")
        create_ref_url = _repository_url(repository, "/git/refs")
        create_ref_body = json.dumps(
            {"ref": f"refs/heads/{BACKUP_BRANCH}", "sha": commit_sha},
            separators=(",", ":"),
        ).encode("utf-8")
        _request(create_ref_url, token, method="POST", body=create_ref_body)
    except urllib.error.HTTPError as error:
        if error.code != 422:
            raise BackupError("GitHub backup branch could not be created.") from error
        try:
            _request(
                _repository_url(repository, f"/git/ref/heads/{BACKUP_BRANCH}"),
                token,
            )
        except urllib.error.HTTPError as branch_error:
            raise BackupError("GitHub backup branch could not be created.") from branch_error
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise BackupError("GitHub returned invalid backup repository metadata.") from error
    _BACKUP_BRANCHES.add(repository)


def _get_backup(repository: str, token: str) -> tuple[str, bytes] | None:
    _ensure_backup_branch(repository, token)
    url = f"{_api_url(repository)}?{urllib.parse.urlencode({'ref': BACKUP_BRANCH})}"
    try:
        response = _request(url, token)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise

    try:
        metadata = json.loads(response)
        if not isinstance(metadata, dict):
            raise ValueError("Invalid file metadata.")
        sha = metadata["sha"]
        if not isinstance(sha, str) or not sha:
            raise ValueError("Missing file SHA.")
        encoded_content = metadata.get("content")
        if not isinstance(encoded_content, str):
            encoded_content = ""
        encoded_content = encoded_content.strip()
        if encoded_content:
            content = base64.b64decode(encoded_content, validate=False)
        else:
            content = _request(
                url,
                token,
                accept="application/vnd.github.raw+json",
            )
        return sha, content
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise BackupError("GitHub returned an invalid database backup file.") from error


def _decrypt_backup(payload: bytes, key: bytes) -> bytes:
    if len(payload) < len(BACKUP_FORMAT) + 12 + 16 or not payload.startswith(BACKUP_FORMAT):
        raise BackupError("The GitHub database backup has an unknown or corrupt format.")
    nonce_start = len(BACKUP_FORMAT)
    nonce = payload[nonce_start : nonce_start + 12]
    ciphertext = payload[nonce_start + 12 :]
    try:
        compressed = AESGCM(key).decrypt(nonce, ciphertext, BACKUP_FORMAT)
    except InvalidTag as error:
        raise BackupError(
            "The GitHub database backup could not be decrypted; check the encryption key."
        ) from error

    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            database = stream.read(MAX_BACKUP_BYTES + 1)
    except (OSError, EOFError, zlib.error) as error:
        raise BackupError("The GitHub database backup is corrupt.") from error
    if len(database) > MAX_BACKUP_BYTES:
        raise BackupError("The restored SQLite database exceeds the 50 MB safety limit.")
    return database


def _encrypt_backup(database: bytes, key: bytes) -> bytes:
    if len(database) > MAX_BACKUP_BYTES:
        raise BackupError("The SQLite database exceeds the 50 MB backup safety limit.")
    compressed = gzip.compress(database, mtime=0)
    nonce = os.urandom(12)
    return BACKUP_FORMAT + nonce + AESGCM(key).encrypt(nonce, compressed, BACKUP_FORMAT)


def restore_sqlite(engine: Engine, settings) -> bool:
    repository, key = validate_backup_settings(settings)
    backup = _get_backup(repository, settings.backup_token.strip())
    if backup is None:
        return False

    database = _decrypt_backup(backup[1], key)
    target = _database_path(engine)
    target.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{target.name}.restore-",
        suffix=".tmp",
        dir=target.parent,
    )
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(database)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        connection = sqlite3.connect(temporary_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if not {"players", "player_kits", "matches"}.issubset(tables):
                raise BackupError("The GitHub backup does not contain GrindPvP player data.")
            result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or result[0] != "ok":
                raise BackupError("The GitHub database backup is not a valid SQLite database.")
        finally:
            connection.close()
        engine.dispose()
        os.replace(temporary_path, target)
        return True
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def save_sqlite(engine: Engine, settings) -> None:
    repository, key = validate_backup_settings(settings)
    token = settings.backup_token.strip()
    source_path = _database_path(engine)
    if not source_path.is_file():
        raise BackupError("The SQLite database file does not exist yet.")

    with _BACKUP_LOCK:
        with tempfile.TemporaryDirectory(prefix="grindpvp-db-backup-") as directory:
            snapshot_path = Path(directory) / "snapshot.sqlite"
            source = sqlite3.connect(source_path)
            snapshot = sqlite3.connect(snapshot_path)
            try:
                source.backup(snapshot)
            finally:
                source.close()
                snapshot.close()
            encrypted = _encrypt_backup(snapshot_path.read_bytes(), key)
            if len(encrypted) > MAX_BACKUP_BYTES:
                raise BackupError("The encrypted GitHub backup exceeds the 50 MB safety limit.")

        url = _api_url(repository)
        for attempt in range(3):
            existing = _get_backup(repository, token)
            body_data: dict[str, str] = {
                "message": "Update encrypted GrindPvP database backup",
                "content": base64.b64encode(encrypted).decode("ascii"),
                "branch": BACKUP_BRANCH,
            }
            if existing is not None:
                body_data["sha"] = existing[0]
            body = json.dumps(body_data, separators=(",", ":")).encode("utf-8")
            try:
                _request(url, token, method="PUT", body=body)
                return
            except urllib.error.HTTPError as error:
                if error.code not in {409, 422} or attempt == 2:
                    raise BackupError(
                        f"GitHub rejected the database backup with HTTP {error.code}."
                    ) from error
        raise BackupError("GitHub database backup failed after repeated file conflicts.")
