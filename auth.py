"""Email + password authentication and Streamlit session management.

Accounts are created by an administrator (there is no payment integration
yet), so self-service sign-up is deliberately absent:

    python auth.py add-user alice@example.com --tier paid
    python auth.py set-tier alice@example.com free
    python auth.py reset-password alice@example.com
    python auth.py disable alice@example.com
    python auth.py list

Inside Docker prefix these with `docker compose exec app`.

Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes (stdlib only, so it
behaves identically on Windows, macOS and Linux). Repeated failures lock an
email out for a while. The logged-in identity lives in st.session_state, which
Streamlit keeps server-side per browser session; the user record is re-read on
every run so a downgrade or disable takes effect immediately.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import re
import secrets
import sqlite3
import sys
import time
from dataclasses import dataclass

import config

PBKDF2_ITERATIONS = 600_000
MIN_PASSWORD_LENGTH = 10
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SESSION_KEY = "_auth"


@dataclass(frozen=True)
class User:
    email: str
    tier: str
    disabled: bool

    @property
    def is_paid(self) -> bool:
        return self.tier == "paid" and not self.disabled


class AuthError(Exception):
    """Shown to the user as-is, so messages never reveal whether an email exists."""


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the email is unknown, so response time does not reveal
# which emails have accounts.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# ---------------------------------------------------------------------------
# User store
# ---------------------------------------------------------------------------

def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> str:
    email = normalize_email(email)
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise AuthError("Enter a valid email address.")
    return email


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def get_user(email: str) -> User | None:
    with config.connect() as con:
        row = con.execute("SELECT email, tier, disabled FROM users WHERE email = ?",
                          (normalize_email(email),)).fetchone()
    return User(row["email"], row["tier"], bool(row["disabled"])) if row else None


def create_user(email: str, password: str, tier: str = "free") -> User:
    email = validate_email(email)
    validate_password(password)
    if tier not in ("free", "paid"):
        raise AuthError("Tier must be 'free' or 'paid'.")
    with config.connect() as con:
        try:
            con.execute("INSERT INTO users (email, password_hash, tier) VALUES (?, ?, ?)",
                        (email, hash_password(password), tier))
        except sqlite3.IntegrityError as exc:
            raise AuthError(f"An account for {email} already exists.") from exc
    return User(email, tier, False)


def set_tier(email: str, tier: str) -> None:
    if tier not in ("free", "paid"):
        raise AuthError("Tier must be 'free' or 'paid'.")
    _update(email, "UPDATE users SET tier = ? WHERE email = ?", (tier, normalize_email(email)))


def set_disabled(email: str, disabled: bool) -> None:
    _update(email, "UPDATE users SET disabled = ? WHERE email = ?", (int(disabled), normalize_email(email)))


def set_password(email: str, password: str) -> None:
    validate_password(password)
    _update(email, "UPDATE users SET password_hash = ? WHERE email = ?",
            (hash_password(password), normalize_email(email)))


def _update(email: str, sql: str, params: tuple) -> None:
    with config.connect() as con:
        if con.execute(sql, params).rowcount == 0:
            raise AuthError(f"No account for {normalize_email(email)}.")


def list_users() -> list[dict]:
    with config.connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT email, tier, disabled, created_at FROM users ORDER BY email")]


# ---------------------------------------------------------------------------
# Login with lockout
# ---------------------------------------------------------------------------

def _recent_failures(con, email: str) -> int:
    since = time.time() - config.LOGIN_LOCKOUT_MINUTES * 60
    con.execute("DELETE FROM login_failures WHERE ts < ?", (since,))
    return con.execute("SELECT COUNT(*) FROM login_failures WHERE email = ? AND ts >= ?",
                       (email, since)).fetchone()[0]


def authenticate(email: str, password: str) -> User:
    email = normalize_email(email)
    generic = AuthError("Incorrect email or password.")
    if not email or not password:
        raise generic
    with config.connect() as con:
        if _recent_failures(con, email) >= config.LOGIN_MAX_FAILURES:
            raise AuthError(f"Too many failed attempts. Try again in {config.LOGIN_LOCKOUT_MINUTES} minutes.")
        row = con.execute("SELECT email, password_hash, tier, disabled FROM users WHERE email = ?",
                          (email,)).fetchone()
        ok = verify_password(password, row["password_hash"] if row else _DUMMY_HASH) and row is not None
        if not ok:
            con.execute("INSERT INTO login_failures (email, ts) VALUES (?, ?)", (email, time.time()))
            raise generic
        con.execute("DELETE FROM login_failures WHERE email = ?", (email,))
    if row["disabled"]:
        raise AuthError("This account is disabled. Contact your administrator.")
    return User(row["email"], row["tier"], False)


# ---------------------------------------------------------------------------
# Streamlit session
# ---------------------------------------------------------------------------

def login(user: User) -> None:
    import streamlit as st
    st.session_state[SESSION_KEY] = {"email": user.email, "last_seen": time.time()}


def logout() -> None:
    import streamlit as st
    st.session_state.pop(SESSION_KEY, None)


def current_user() -> User | None:
    """The signed-in user, re-read from the database; None after idle timeout,
    deletion or disabling."""
    import streamlit as st
    sess = st.session_state.get(SESSION_KEY)
    if not sess:
        return None
    now = time.time()
    if now - sess["last_seen"] > config.SESSION_IDLE_MINUTES * 60:
        logout()
        st.session_state["_auth_msg"] = "Your session expired. Please sign in again."
        return None
    user = get_user(sess["email"])
    if user is None or user.disabled:
        logout()
        return None
    sess["last_seen"] = now
    return user


# ---------------------------------------------------------------------------
# Admin CLI
# ---------------------------------------------------------------------------

def _prompt_password() -> str:
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Repeat password: "):
        raise AuthError("Passwords do not match.")
    return pw


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python auth.py", description="Manage Stockera user accounts.")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-user", help="create an account (prompts for the password)")
    a.add_argument("email")
    a.add_argument("--tier", choices=["free", "paid"], default="paid")
    t = sub.add_parser("set-tier", help="upgrade or downgrade an account")
    t.add_argument("email")
    t.add_argument("tier", choices=["free", "paid"])
    for name, text in (("reset-password", "set a new password"), ("disable", "block sign-in"),
                       ("enable", "allow sign-in again")):
        sub.add_parser(name, help=text).add_argument("email")
    sub.add_parser("list", help="list accounts with this month's token usage")
    args = p.parse_args(argv)

    config.init_db()
    try:
        if args.cmd == "add-user":
            validate_email(args.email)
            user = create_user(args.email, _prompt_password(), args.tier)
            print(f"Created {user.email} ({user.tier}).")
        elif args.cmd == "set-tier":
            set_tier(args.email, args.tier)
            print(f"{normalize_email(args.email)} is now {args.tier}.")
        elif args.cmd == "reset-password":
            if get_user(args.email) is None:
                raise AuthError(f"No account for {normalize_email(args.email)}.")
            set_password(args.email, _prompt_password())
            print("Password updated.")
        elif args.cmd in ("disable", "enable"):
            set_disabled(args.email, args.cmd == "disable")
            print(f"{normalize_email(args.email)} {args.cmd}d.")
        elif args.cmd == "list":
            import token_counter
            rows = list_users()
            if not rows:
                print("No accounts yet. Create one with: python auth.py add-user EMAIL --tier paid")
            for r in rows:
                used = token_counter.used_this_month(r["email"])
                flag = " (disabled)" if r["disabled"] else ""
                print(f"{r['email']:<40} {r['tier']:<5} {used:>6,}/{config.MONTHLY_TOKEN_LIMIT:,} tokens{flag}")
    except AuthError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
