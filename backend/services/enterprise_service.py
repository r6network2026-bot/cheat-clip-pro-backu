import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

SESSION_LIFETIME = timedelta(days=7)
PASSWORD_ITERATIONS = 310_000
MAX_PROJECT_ASSET_BYTES = 5 * 1024 * 1024
SESSION_COOKIE = "cheat_clip_session"


def _database_path() -> Path:
    configured_path = os.environ.get("ENTERPRISE_DB_PATH", "").strip()
    backend_dir = Path(__file__).resolve().parents[1]
    path = Path(configured_path) if configured_path else backend_dir / "data" / "enterprise.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(_database_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_system_admin INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions(expires_at);
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_members (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('owner', 'admin', 'editor', 'viewer')),
                joined_at TEXT NOT NULL,
                PRIMARY KEY(project_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS project_assets (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                asset_type TEXT NOT NULL CHECK(asset_type IN ('analysis', 'render_settings')),
                value_json TEXT NOT NULL,
                updated_by TEXT NOT NULL REFERENCES users(id),
                updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id, asset_type)
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                actor_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                actor_email TEXT NOT NULL,
                action TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS audit_project_created_idx ON audit_events(project_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS audit_actor_created_idx ON audit_events(actor_id, created_at DESC);
            """
        )
        user_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(users)")
        }
        if "is_system_admin" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN is_system_admin INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute(
            """
            UPDATE users SET is_system_admin = 1
            WHERE id = (
                SELECT id FROM users ORDER BY created_at, id LIMIT 1
            )
            AND NOT EXISTS (SELECT 1 FROM users WHERE is_system_admin = 1)
            """
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${derived_key.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    algorithm, iterations, salt_hex, expected_hex = encoded_hash.split("$", 3)
    if algorithm != "pbkdf2_sha256":
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
    )
    return hmac.compare_digest(actual.hex(), expected_hex)


def issue_session(connection: sqlite3.Connection, user_id: str) -> str:
    raw_token = secrets.token_urlsafe(32)
    created_at = now_iso()
    expires_at = (datetime.now(timezone.utc) + SESSION_LIFETIME).isoformat()
    connection.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (hashlib.sha256(raw_token.encode()).hexdigest(), user_id, expires_at, created_at),
    )
    connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (created_at,))
    return raw_token


def resolve_session(raw_token: str | None) -> dict[str, Any] | None:
    if not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT users.id, users.email, users.display_name, users.is_system_admin
            FROM sessions JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, now_iso()),
        ).fetchone()
    if not row:
        return None
    user = dict(row)
    user["is_system_admin"] = bool(user["is_system_admin"])
    return user


def revoke_session(raw_token: str | None) -> None:
    if not raw_token:
        return
    with connect() as connection:
        connection.execute(
            "DELETE FROM sessions WHERE token_hash = ?",
            (hashlib.sha256(raw_token.encode()).hexdigest(),),
        )


def record_audit(
    connection: sqlite3.Connection,
    project_id: str | None,
    actor_id: str | None,
    actor_email: str,
    action: str,
    details: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_events (project_id, actor_id, actor_email, action, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, actor_id, actor_email, action, json.dumps(details or {}), now_iso()),
    )


def safe_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, str]:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
    }


initialize_database()
