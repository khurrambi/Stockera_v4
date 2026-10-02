"""Runtime configuration shared by the paid-tier modules.

All secrets and tunables come from environment variables. For local runs a
`.env` file next to this module is read too (values already set in the real
environment win), so Windows, macOS and Docker are configured the same way.
The Anthropic API key is never stored in code, logged or shown in the UI.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Minimal KEY=VALUE reader (no dependency on python-dotenv)."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


DATA_DIR = Path(os.environ.get("STOCKERA_DATA_DIR") or ROOT / "data")
DB_PATH = DATA_DIR / "stockera.db"

MONTHLY_TOKEN_LIMIT = _int("MONTHLY_TOKEN_LIMIT", 5000)
AGENT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
AGENT_EFFORT = os.environ.get("AGENT_EFFORT", "low")          # sent only to models that support effort (not Haiku 4.5)
AGENT_MAX_OUTPUT_TOKENS = _int("AGENT_MAX_OUTPUT_TOKENS", 1200)
AGENT_MIN_OUTPUT_TOKENS = _int("AGENT_MIN_OUTPUT_TOKENS", 600)   # below this a full report won't fit
# Server-side refusal fallback: only sent for Opus 5 / Fable 5 models on the Claude API.
AGENT_FALLBACKS = os.environ.get("AGENT_FALLBACKS", "1").strip().lower() not in ("0", "false", "no", "off")
SESSION_IDLE_MINUTES = _int("SESSION_IDLE_MINUTES", 60)
LOGIN_MAX_FAILURES = _int("LOGIN_MAX_FAILURES", 5)
LOGIN_LOCKOUT_MINUTES = _int("LOGIN_LOCKOUT_MINUTES", 15)


def api_key_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email          TEXT PRIMARY KEY,
    password_hash  TEXT NOT NULL,
    tier           TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'paid')),
    disabled       INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TABLE IF NOT EXISTS login_failures (
    email  TEXT NOT NULL,
    ts     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_login_failures ON login_failures (email, ts);
CREATE TABLE IF NOT EXISTS token_usage (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT NOT NULL,
    period         TEXT NOT NULL,              -- YYYY-MM (UTC)
    tokens         INTEGER NOT NULL,           -- reserved amount, replaced by actual on settle
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL CHECK (status IN ('reserved', 'settled')),
    model          TEXT,
    request_id     TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS ix_token_usage ON token_usage (email, period);
CREATE TABLE IF NOT EXISTS council_reports (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    dataset_label  TEXT NOT NULL,
    context_sig    TEXT NOT NULL,
    tokens         INTEGER NOT NULL,
    model          TEXT NOT NULL,
    report_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_council_reports ON council_reports (email, created_at);
"""


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript(SCHEMA)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Short-lived connection per operation. Autocommit mode, so callers that
    need atomic read-then-write open their own `BEGIN IMMEDIATE` transaction."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA busy_timeout = 15000")
        yield con
    finally:
        con.close()
