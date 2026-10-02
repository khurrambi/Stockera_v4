"""Persistent per-user monthly token budget (default 5,000 tokens / calendar month, UTC).

Every token Anthropic bills counts: input, cache writes, cache reads and
output (which includes any thinking). Enforcement is reserve-then-settle:

1. `reserve()` claims the worst case (exact input count + max output) inside a
   `BEGIN IMMEDIATE` transaction, so two browser tabs cannot both spend the
   last tokens.
2. The request runs with `max_tokens` capped to what was reserved, so it
   cannot overshoot the budget.
3. `settle()` replaces the reservation with the billed usage, or `release()`
   drops it when the request failed before anything was billed.

Unsettled reservations (e.g. the server was killed mid-request) keep counting
at their reserved size, which errs on the side of the budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import config


class TokenLimitExceeded(Exception):
    def __init__(self, needed: int, remaining: int):
        self.needed, self.remaining = needed, remaining
        super().__init__(f"This request needs up to {needed:,} tokens but only {remaining:,} remain this month.")


@dataclass(frozen=True)
class Usage:
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def fraction(self) -> float:
        return min(1.0, self.used / self.limit) if self.limit else 1.0


def current_period(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def next_reset(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)


def _used(con, email: str, period: str) -> int:
    return con.execute("SELECT COALESCE(SUM(tokens), 0) FROM token_usage WHERE email = ? AND period = ?",
                       (email, period)).fetchone()[0]


def used_this_month(email: str) -> int:
    with config.connect() as con:
        return _used(con, email, current_period())


def get_usage(email: str) -> Usage:
    return Usage(used_this_month(email), config.MONTHLY_TOKEN_LIMIT)


def reserve(email: str, tokens: int, model: str) -> int:
    """Atomically claim `tokens` from this month's budget; returns the reservation id."""
    if tokens <= 0:
        raise ValueError("tokens must be positive")
    period = current_period()
    with config.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            remaining = config.MONTHLY_TOKEN_LIMIT - _used(con, email, period)
            if tokens > remaining:
                raise TokenLimitExceeded(tokens, max(0, remaining))
            cur = con.execute(
                "INSERT INTO token_usage (email, period, tokens, status, model) VALUES (?, ?, ?, 'reserved', ?)",
                (email, period, tokens, model))
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    return int(cur.lastrowid)


def settle(reservation_id: int, input_tokens: int, output_tokens: int, request_id: str | None = None) -> int:
    """Replace a reservation with the billed amount. Returns the billed total."""
    total = int(input_tokens) + int(output_tokens)
    with config.connect() as con:
        con.execute(
            "UPDATE token_usage SET tokens = ?, input_tokens = ?, output_tokens = ?, status = 'settled', "
            "request_id = ? WHERE id = ?",
            (total, int(input_tokens), int(output_tokens), request_id, reservation_id))
    return total


def release(reservation_id: int) -> None:
    """Drop a reservation for a request that was not billed (e.g. network or 5xx error)."""
    with config.connect() as con:
        con.execute("DELETE FROM token_usage WHERE id = ? AND status = 'reserved'", (reservation_id,))


def history(email: str, limit: int = 20) -> list[dict]:
    with config.connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT created_at, tokens, input_tokens, output_tokens, status, model FROM token_usage "
            "WHERE email = ? ORDER BY id DESC LIMIT ?", (email, limit))]
