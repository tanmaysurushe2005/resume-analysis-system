"""Framework-agnostic application service functions for future API adapters."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from . import cache
from .batch import run_batch
from .documents import read_document
from .llm import get_llm
from .models import JobSpec, Report
from .pipeline import Analyzer
from .sanitize import sanitize

_analyzer: Analyzer | None = None


def _get_analyzer() -> Analyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = Analyzer(get_llm())
    return _analyzer


def _job_record(job_id: str) -> dict[str, Any]:
    for record in cache.list_jobs():
        if record["job_id"] == job_id:
            return record
    raise KeyError(f"Unknown job: {job_id}")


def _job_spec(job_id: str) -> JobSpec:
    return JobSpec.model_validate(json.loads(_job_record(job_id)["parsed_json"]))


def create_job(title_or_text: str) -> str:
    analyzer = _get_analyzer()
    analyzer.parse_job(title_or_text)
    return cache.job_id(title_or_text)


def list_jobs() -> list[dict[str, Any]]:
    return [
        {
            "job_id": row["job_id"],
            "raw_text": row["raw_text"],
            "prompt_version": row["prompt_version"],
            "created_at": row["created_at"],
        }
        for row in cache.list_jobs()
    ]


def submit_batch(job_id: str, resumes: list[str | Path]) -> str:
    job = _job_spec(job_id)
    batch_id = uuid.uuid4().hex
    entries = [
        {
            "resume_ref": Path(resume).name if isinstance(resume, Path) else f"resume-{i + 1}",
            "resume_text": (
                read_document(resume)
                if isinstance(resume, Path) else resume
            ),
        }
        for i, resume in enumerate(resumes)
    ]
    cache.put_batch(batch_id, job_id, entries)
    analyzer = _get_analyzer()

    def persist(result: dict[str, Any]) -> None:
        report = result.get("report")
        cache.update_batch_resume(
            batch_id,
            result["name"],
            result["status"],
            result.get("error"),
            report.model_dump() if report else None,
        )

    run_batch(
        [entry["resume_text"] for entry in entries],
        job,
        analyzer,
        persist,
        resume_refs=[entry["resume_ref"] for entry in entries],
    )
    return batch_id


def get_batch(batch_id: str) -> dict[str, Any]:
    result = cache.get_batch(batch_id)
    if result is None:
        raise KeyError(f"Unknown batch: {batch_id}")
    return result


def get_ranked_results(batch_id: str) -> list[dict[str, Any]]:
    results = [
        {
            **row,
            "report": Report.model_validate(json.loads(row["report_json"]))
            if row["report_json"] else None,
        }
        for row in get_batch(batch_id)["resumes"]
        if row["report_json"]
    ]
    return sorted(results, key=lambda row: -row["report"].match_score)


def get_candidate(candidate_ref: str) -> Report:
    for row in cache.list_batch_reports():
        report = Report.model_validate(json.loads(row["report_json"]))
        if report.candidate_ref == candidate_ref:
            return report
    raise KeyError(f"Unknown candidate: {candidate_ref}")


def recommend_candidate(candidate_ref: str) -> Report:
    report = get_candidate(candidate_ref)
    if report.recommendation is not None:
        return report
    analyzer = _get_analyzer()
    for row in cache.list_batch_reports():
        if json.loads(row["report_json"]).get("candidate_ref") == candidate_ref:
            batch = cache.get_batch(row["batch_id"])
            if batch is not None:
                report = analyzer.recommend(report, _job_spec(batch["job_id"]))
                cache.update_batch_resume(
                    row["batch_id"], row["resume_ref"], "done",
                    report_json=report.model_dump(),
                )
                return report
    raise KeyError(f"Unknown candidate: {candidate_ref}")
