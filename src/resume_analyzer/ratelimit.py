"""Persistent request pacing and daily budgets for real providers."""
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from . import cache


class DailyLimitReached(RuntimeError):
    """Raised when the configured daily request budget is exhausted."""


class RateLimiter:
    def __init__(
        self,
        rpm: int | None = None,
        daily_limit: int | None = None,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
        date_fn: Callable[[], str] | None = None,
    ):
        self.rpm = rpm if rpm is not None else int(os.getenv("RA_RPM", "8"))
        self.daily_limit = (
            daily_limit if daily_limit is not None
            else int(os.getenv("RA_DAILY_LIMIT", "490"))
        )
        self.clock = clock or time.monotonic
        self.sleeper = sleeper or time.sleep
        self.date_fn = date_fn or self._pacific_date
        self.last_call: float | None = None

    @staticmethod
    def _pacific_date() -> str:
        return datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()

    @property
    def interval(self) -> float:
        return 60 / self.rpm if self.rpm > 0 else 0

    def acquire(self) -> None:
        today = self.date_fn()
        used = cache.get_daily_count(today)
        if used >= self.daily_limit:
            raise DailyLimitReached(
                f"Daily API limit reached for {today}: {used}/{self.daily_limit} calls."
            )
        now = self.clock()
        if self.last_call is not None:
            wait = self.interval - (now - self.last_call)
            if wait > 0:
                self.sleeper(wait)
                now = self.clock()
        cache.increment_daily_count(today)
        self.last_call = now
