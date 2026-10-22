"""Sequential batch processing with per-resume outcomes."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .models import JobSpec, Report
from .ratelimit import DailyLimitReached
from .documents import read_document


def run_batch(
    resume_paths_or_texts: Iterable[str | Path],
    job: JobSpec,
    analyzer: Any,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    with_recommendations: bool = False,
    resume_refs: list[str] | None = None,
) -> list[dict[str, Any]]:
    items = list(resume_paths_or_texts)
    results: list[dict[str, Any]] = []
    stopped = False
    for index, item in enumerate(items):
        name = (
            resume_refs[index] if resume_refs else
            (Path(item).name if isinstance(item, Path) else "resume")
        )
        if stopped:
            results.append({"name": name, "status": "queued"})
            continue
        try:
            text = read_document(item) if isinstance(item, Path) else item
            report: Report = analyzer.analyze(text, job)
            if (
                with_recommendations
                and report.tier in {"Strong Advance", "Advance"}
                and report.recommendation is None
            ):
                report = analyzer.recommend(report, job)
            status = "cached" if report.meta.get("cached") else "done"
            result = {"name": name, "status": status, "report": report}
        except DailyLimitReached as err:
            stopped = True
            result = {"name": name, "status": "queued", "error": str(err)}
        except Exception as err:  # one bad resume must not stop the batch
            result = {"name": name, "status": "failed", "error": str(err)}
        results.append(result)
        if on_progress:
            on_progress(result)
    return results
