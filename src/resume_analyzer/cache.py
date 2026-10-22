"""Persistent SQLite cache for parsed jobs and analysis reports."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _path() -> Path:
    return Path(os.getenv("RA_CACHE_PATH", ".cache/ra.sqlite3"))


def _connect() -> sqlite3.Connection:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            raw_text TEXT NOT NULL,
            parsed_json TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS results (
            key TEXT PRIMARY KEY,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            thinking_tokens INTEGER NOT NULL,
            latency_ms REAL NOT NULL,
            cache_hit INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily_usage (
            usage_date TEXT PRIMARY KEY,
            call_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS batch_resumes (
            batch_id TEXT NOT NULL,
            resume_ref TEXT NOT NULL,
            resume_text TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            report_json TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, resume_ref)
        );
        """
    )
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_job_text(raw_text: str) -> str:
    return " ".join(raw_text.split())


def job_id(raw_text: str) -> str:
    return hashlib.sha256(normalize_job_text(raw_text).encode("utf-8")).hexdigest()


def resume_hash(redacted_text: str) -> str:
    return hashlib.sha256(redacted_text.encode("utf-8")).hexdigest()


def result_key(redacted_text: str, cached_job_id: str, prompt_version: str, model: str) -> str:
    value = "\0".join((redacted_text, cached_job_id, prompt_version, model))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_job(raw_text: str) -> dict[str, Any] | None:
    cached_id = job_id(raw_text)
    with _connect() as conn:
        row = conn.execute(
            "SELECT job_id, raw_text, parsed_json, prompt_version, created_at "
            "FROM jobs WHERE job_id = ?",
            (cached_id,),
        ).fetchone()
    return dict(row) if row else None


def put_job(raw_text: str, parsed_json: dict[str, Any], prompt_version: str) -> str:
    cached_id = job_id(raw_text)
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO jobs "
            "(job_id, raw_text, parsed_json, prompt_version, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (cached_id, raw_text, json.dumps(parsed_json), prompt_version, _now()),
        )
    return cached_id


def get_result(key: str) -> dict[str, Any] | None:
    if os.getenv("RA_CACHE_DISABLED") == "1":
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT key, report_json, created_at FROM results WHERE key = ?",
            (key,),
        ).fetchone()
    return dict(row) if row else None


def put_result(key: str, report_json: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO results (key, report_json, created_at) "
            "VALUES (?, ?, ?)",
            (key, json.dumps(report_json), _now()),
        )


def put_usage(record: Any) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO usage "
            "(task, model, input_tokens, output_tokens, thinking_tokens, "
            "latency_ms, cache_hit, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.task,
                record.model,
                record.input_tokens,
                record.output_tokens,
                record.thinking_tokens,
                record.latency_ms,
                int(record.cache_hit),
                _now(),
            ),
        )


def get_daily_count(usage_date: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT call_count FROM daily_usage WHERE usage_date = ?",
            (usage_date,),
        ).fetchone()
    return int(row["call_count"]) if row else 0


def list_jobs() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT job_id, raw_text, parsed_json, prompt_version, created_at "
            "FROM jobs ORDER BY created_at"
        ).fetchall()
    return [dict(row) for row in rows]


def get_batch(batch_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        batch = conn.execute(
            "SELECT batch_id, job_id, created_at FROM batches WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
        if not batch:
            return None
        rows = conn.execute(
            "SELECT resume_ref, status, error, report_json, created_at "
            "FROM batch_resumes WHERE batch_id = ? ORDER BY rowid",
            (batch_id,),
        ).fetchall()
    result = dict(batch)
    result["resumes"] = [dict(row) for row in rows]
    return result


def list_batches() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT batch_id, job_id, created_at FROM batches ORDER BY created_at"
        ).fetchall()
    return [dict(row) for row in rows]


def list_batch_reports() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT batch_id, resume_ref, status, error, report_json, created_at "
            "FROM batch_resumes WHERE report_json IS NOT NULL ORDER BY created_at"
        ).fetchall()
    return [dict(row) for row in rows]


def put_batch(batch_id: str, cached_job_id: str, resumes: list[dict[str, Any]]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO batches (batch_id, job_id, created_at) VALUES (?, ?, ?)",
            (batch_id, cached_job_id, _now()),
        )
        conn.executemany(
            "INSERT INTO batch_resumes "
            "(batch_id, resume_ref, resume_text, status, error, report_json, created_at) "
            "VALUES (?, ?, ?, ?, NULL, NULL, ?)",
            [
                (batch_id, item["resume_ref"], item["resume_text"], "queued", _now())
                for item in resumes
            ],
        )


def update_batch_resume(
    batch_id: str,
    resume_ref: str,
    status: str,
    error: str | None = None,
    report_json: dict[str, Any] | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE batch_resumes SET status = ?, error = ?, report_json = ? "
            "WHERE batch_id = ? AND resume_ref = ?",
            (
                status,
                error,
                json.dumps(report_json) if report_json is not None else None,
                batch_id,
                resume_ref,
            ),
        )


def increment_daily_count(usage_date: str) -> int:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO daily_usage (usage_date, call_count) VALUES (?, 1) "
            "ON CONFLICT(usage_date) DO UPDATE SET call_count = call_count + 1",
            (usage_date,),
        )
        row = conn.execute(
            "SELECT call_count FROM daily_usage WHERE usage_date = ?",
            (usage_date,),
        ).fetchone()
    return int(row["call_count"])


def already_analysed(
    redacted_text: str, cached_job_id: str, prompt_version: str, model: str
) -> bool:
    return get_result(result_key(redacted_text, cached_job_id, prompt_version, model)) is not None


def clear() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM jobs")
        conn.execute("DELETE FROM results")
        conn.execute("DELETE FROM usage")
        conn.execute("DELETE FROM daily_usage")
        conn.execute("DELETE FROM batch_resumes")
        conn.execute("DELETE FROM batches")
