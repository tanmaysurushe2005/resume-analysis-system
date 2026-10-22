"""In-memory and SQLite-backed model usage tracking."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from . import cache


@dataclass
class UsageRecord:
    task: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    latency_ms: float = 0.0
    cache_hit: bool = False


@dataclass
class UsageTracker:
    records: list[UsageRecord] = field(default_factory=list)

    def record(
        self,
        task: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        thinking_tokens: int = 0,
        latency_ms: float = 0.0,
        cache_hit: bool = False,
    ) -> UsageRecord:
        record = UsageRecord(
            task=task,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
        )
        self.records.append(record)
        cache.put_usage(record)
        return record

    def record_cache_hit(self, task: str, model: str) -> UsageRecord:
        return self.record(task=task, model=model, cache_hit=True)

    def summary(self) -> dict[str, Any]:
        return {
            "calls": sum(not r.cache_hit for r in self.records),
            "input_tokens": sum(r.input_tokens for r in self.records),
            "output_tokens": sum(r.output_tokens for r in self.records),
            "thinking_tokens": sum(r.thinking_tokens for r in self.records),
            "cache_hits": sum(r.cache_hit for r in self.records),
            "cache_misses": sum(not r.cache_hit for r in self.records),
            "latency_ms": round(sum(r.latency_ms for r in self.records), 2),
        }


def elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000
