"""Pure builders for dashboard tables and downloads."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Iterable

from resume_analyzer.models import JobSpec, Report
from resume_analyzer.report import render_markdown


ADVISORY_LINE = "Advisory recommendation - human review required"


def _metadata(job: JobSpec, model: str, prompt_version: str, generated_at: str) -> str:
    return (
        f"Job title: {job.title}\n"
        f"Model: {model}\n"
        f"Prompt version: {prompt_version}\n"
        f"Generated at: {generated_at}\n"
        f"{ADVISORY_LINE}\n"
    )


def ranking_rows(rows: Iterable[tuple[str, Report]]) -> list[dict[str, object]]:
    return [
        {
            "Rank": rank,
            "Candidate": name,
            "Score": report.match_score,
            "Recommended tier": report.tier,
            "Review flag": "Needs human review" if report.needs_human_review else "",
            "Status": "complete",
        }
        for rank, (name, report) in enumerate(
            sorted(rows, key=lambda item: -item[1].match_score), start=1
        )
    ]


def comparison_rows(
    job: JobSpec, rows: Iterable[tuple[str, Report]]
) -> list[dict[str, str]]:
    candidates = list(rows)
    output = []
    for requirement in job.requirements:
        row = {"Requirement": f"{requirement.id} ({requirement.type}): {requirement.text}"}
        for name, report in candidates:
            match = next(
                item for item in report.matches
                if item.requirement_id == requirement.id
            )
            row[name] = f"{match.score}/4" + (
                " - MISSING" if requirement.type == "must" and match.score == 0 else ""
            )
        output.append(row)
    return output


def ranking_csv(
    rows: Iterable[tuple[str, Report]],
    job: JobSpec,
    model: str,
    prompt_version: str,
    generated_at: str | None = None,
) -> bytes:
    generated_at = generated_at or datetime.now().astimezone().isoformat()
    output = io.StringIO()
    output.write(_metadata(job, model, prompt_version, generated_at))
    writer = csv.DictWriter(output, fieldnames=[
        "Rank", "Candidate", "Score", "Recommended tier", "Review flag", "Status",
    ])
    writer.writeheader()
    writer.writerows(ranking_rows(rows))
    return output.getvalue().encode("utf-8")


def ranking_excel(
    rows: Iterable[tuple[str, Report]],
    job: JobSpec,
    model: str,
    prompt_version: str,
    generated_at: str | None = None,
) -> bytes:
    from openpyxl import Workbook

    generated_at = generated_at or datetime.now().astimezone().isoformat()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Ranking"
    metadata = [
        ("Job title", job.title),
        ("Model", model),
        ("Prompt version", prompt_version),
        ("Generated at", generated_at),
        ("Notice", ADVISORY_LINE),
    ]
    for row in metadata:
        sheet.append(row)
    sheet.append([])
    headers = ["Rank", "Candidate", "Score", "Recommended tier", "Review flag", "Status"]
    sheet.append(headers)
    for row in ranking_rows(rows):
        sheet.append([row[header] for header in headers])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def comparison_csv(
    job: JobSpec,
    rows: Iterable[tuple[str, Report]],
    model: str,
    prompt_version: str,
    generated_at: str | None = None,
) -> bytes:
    generated_at = generated_at or datetime.now().astimezone().isoformat()
    rows = list(rows)
    comparison = comparison_rows(job, rows)
    headers = ["Requirement"] + [name for name, _ in rows]
    output = io.StringIO()
    output.write(_metadata(job, model, prompt_version, generated_at))
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(comparison)
    return output.getvalue().encode("utf-8")


def candidate_markdown(
    name: str,
    report: Report,
    job: JobSpec,
    model: str,
    prompt_version: str,
    generated_at: str | None = None,
) -> bytes:
    generated_at = generated_at or datetime.now().astimezone().isoformat()
    content = _metadata(job, model, prompt_version, generated_at)
    content += f"\n# Candidate: {name}\n\n{render_markdown(report, job)}\n"
    return content.encode("utf-8")


def combined_markdown(
    rows: Iterable[tuple[str, Report]],
    job: JobSpec,
    model: str,
    prompt_version: str,
    generated_at: str | None = None,
) -> bytes:
    generated_at = generated_at or datetime.now().astimezone().isoformat()
    content = _metadata(job, model, prompt_version, generated_at)
    content += "\n" + "\n\n".join(
        f"# Candidate: {name}\n\n{render_markdown(report, job)}"
        for name, report in rows
    )
    return content.encode("utf-8")
