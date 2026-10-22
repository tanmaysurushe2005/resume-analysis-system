"""Streamlit front end for the Resume Analysis system."""
from __future__ import annotations

import os
from datetime import datetime

import streamlit as st

from resume_analyzer import prompts
from resume_analyzer.cache import get_daily_count
from resume_analyzer.llm import get_llm
from resume_analyzer.models import JobSpec, Report
from resume_analyzer.pipeline import Analyzer
from resume_analyzer.ratelimit import RateLimiter
from resume_analyzer.readers import read_resume_file, read_resume_files
from dashboard_logic import (
    candidate_markdown,
    combined_markdown,
    comparison_csv,
    ranking_csv,
    ranking_excel,
)


PRIVACY_NOTICE = (
    "Resumes are sent to the configured AI provider. Use only synthetic or consented data."
)


@st.cache_resource
def get_dashboard_llm():
    return get_llm()


@st.cache_resource
def get_dashboard_analyzer():
    return Analyzer(get_dashboard_llm())


def _daily_calls_remaining(rate_limiter: RateLimiter) -> int:
    used = get_daily_count(rate_limiter.date_fn())
    return max(rate_limiter.daily_limit - used, 0)


def _read_job_upload(uploaded_file) -> tuple[str, str | None]:
    try:
        entries = read_resume_file(uploaded_file.name, uploaded_file.getvalue())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return "", str(exc)
    if not entries:
        return "", f"{uploaded_file.name}: no text found."
    return entries[0][1], None


st.set_page_config(page_title="Resume Analysis", page_icon="📄", layout="wide")
st.title("Resume Analysis")
st.info(PRIVACY_NOTICE)
st.caption("Advisory recommendation - human review required.")

llm = get_dashboard_llm()
rate_limiter = RateLimiter()
with st.sidebar:
    st.header("System")
    st.write(f"Provider: `{os.getenv('RA_PROVIDER') or 'automatic/mock fallback'}`")
    st.write(f"Model: `{llm.name}`")
    st.write(f"Prompt version: `{prompts.PROMPT_VERSION}`")
    st.write(f"Daily calls remaining: **{_daily_calls_remaining(rate_limiter)}**")

st.header("Job")
job_title = st.text_input("Job title")
job_upload = st.file_uploader(
    "Upload job description (optional)",
    type=["txt", "pdf", "docx"],
    accept_multiple_files=False,
)
uploaded_job_text = ""
if job_upload is not None:
    uploaded_job_text, job_error = _read_job_upload(job_upload)
    if job_error:
        st.error(job_error)
    else:
        st.success(f"Read job description from {job_upload.name}.")

job_description = st.text_area(
    "Job description",
    value=uploaded_job_text,
    height=220,
    help="Paste a job description or upload one above.",
)

st.header("Resumes")
resume_uploads = st.file_uploader(
    "Upload resumes",
    type=["txt", "md", "pdf", "docx", "csv"],
    accept_multiple_files=True,
)

resume_entries: list[tuple[str, str]] = []
resume_errors: list[tuple[str, str]] = []
if resume_uploads:
    resume_entries, resume_errors = read_resume_files(
        (uploaded_file.name, uploaded_file.getvalue())
        for uploaded_file in resume_uploads
    )

preview_rows = [
    {"Candidate": label, "Status": "ready", "Error": ""}
    for label, _ in resume_entries
]
preview_rows.extend(
    {"Candidate": filename, "Status": "error", "Error": error}
    for filename, error in resume_errors
)
if preview_rows:
    st.subheader("Files read")
    st.dataframe(preview_rows, use_container_width=True, hide_index=True)

candidate_count = len(resume_entries)
expected_calls = 1 + (2 * candidate_count) if job_description.strip() and candidate_count else 0
remaining_calls = _daily_calls_remaining(rate_limiter)
if expected_calls:
    st.write(f"Expected model calls for this run: **{expected_calls}**")
    if expected_calls > remaining_calls:
        st.warning(
            f"This run may exceed the remaining daily budget "
            f"({remaining_calls} calls remaining)."
        )

can_analyze = bool(job_title.strip() and job_description.strip() and resume_entries)
if "dashboard_results" not in st.session_state:
    st.session_state.dashboard_results = []
if "dashboard_job" not in st.session_state:
    st.session_state.dashboard_job = None

analyze_clicked = st.button(
    "Analyze",
    disabled=not can_analyze,
    help="Provide a job title, job description, and at least one readable resume.",
)
if analyze_clicked:
    analyzer = get_dashboard_analyzer()
    progress = st.progress(0)
    status_line = st.empty()
    run_results: list[dict] = []

    try:
        status_line.write("Parsing the job description...")
        job = analyzer.parse_job(job_description)

        def on_progress(result: dict) -> None:
            run_results.append(result)
            processed = len(run_results)
            progress.progress(processed / len(resume_entries))
            status_line.write(f"Processed {processed}/{len(resume_entries)}: {result['name']}")

        from resume_analyzer.batch import run_batch

        batch_results = run_batch(
            [text for _, text in resume_entries],
            job,
            analyzer,
            on_progress=on_progress,
            with_recommendations=True,
            resume_refs=[label for label, _ in resume_entries],
        )
        normalized_results = []
        for result in batch_results:
            report = result.get("report")
            normalized_results.append({
                "name": result["name"],
                "status": (
                    "not processed" if result["status"] == "queued"
                    else result["status"]
                ),
                "error": result.get("error"),
                "report": report.model_dump() if isinstance(report, Report) else None,
            })
        st.session_state.dashboard_results = normalized_results
        st.session_state.dashboard_job = job.model_dump()
        progress.progress(1.0)
        status_line.success("Analysis complete. Human review is required for every decision.")
    except Exception as exc:
        st.session_state.dashboard_results = [
            {
                "name": label,
                "status": "not processed",
                "error": str(exc),
                "report": None,
            }
            for label, _ in resume_entries
        ]
        status_line.error(f"Analysis could not complete: {exc}")
    st.rerun()

if st.session_state.dashboard_results:
    st.subheader("Analysis status")
    st.dataframe(
        [
            {
                "Candidate": result["name"],
                "Status": result["status"],
                "Error": result.get("error") or "",
            }
            for result in st.session_state.dashboard_results
        ],
        use_container_width=True,
        hide_index=True,
    )

    stored_job = JobSpec.model_validate(st.session_state.dashboard_job)
    report_rows = [
        (result["name"], Report.model_validate(result["report"]))
        for result in st.session_state.dashboard_results
        if result.get("report")
    ]
    if report_rows:
        st.subheader("Results")
        tiers = ["Strong Advance", "Advance", "Hold", "Decline"]
        selected_tiers = st.multiselect("Filter by tier", tiers, default=tiers)
        review_filter = st.checkbox("Show only candidates needing human review")
        filtered_rows = [
            (name, report)
            for name, report in report_rows
            if report.tier in selected_tiers
            and (not review_filter or report.needs_human_review)
        ]
        ranking_rows = []
        for rank, (name, report) in enumerate(
            sorted(filtered_rows, key=lambda item: -item[1].match_score), start=1
        ):
            ranking_rows.append({
                "Rank": rank,
                "Candidate": name,
                "Score": report.match_score,
                "Recommended tier": report.tier,
                "Review flag": "Needs human review" if report.needs_human_review else "",
                "Status": next(
                    result["status"]
                    for result in st.session_state.dashboard_results
                    if result["name"] == name
                ),
            })
        st.dataframe(ranking_rows, use_container_width=True, hide_index=True)

        if filtered_rows:
            selected_name = st.selectbox(
                "Candidate detail",
                [name for name, _ in filtered_rows],
            )
            selected_report = next(
                report for name, report in filtered_rows if name == selected_name
            )
            st.write(
                f"Recommended: **{selected_report.tier}** "
                "(a human must make every decision)."
            )
            if selected_report.needs_human_review or selected_report.profile.integrity_flags:
                st.warning("Needs human review")
            if selected_report.review_reasons:
                st.write("Review reasons:")
                for reason in selected_report.review_reasons:
                    st.write(f"- {reason}")

            st.markdown("#### Requirement breakdown")
            requirement_by_id = {requirement.id: requirement for requirement in stored_job.requirements}
            for match in selected_report.matches:
                requirement = requirement_by_id[match.requirement_id]
                with st.expander(
                    f"{requirement.id} ({requirement.type}) - {requirement.text}: "
                    f"{match.score}/4, {match.confidence}"
                ):
                    st.write(f"**Reasoning:** {match.reasoning or 'No reasoning returned.'}")
                    st.write("**Evidence quotes:**")
                    if match.evidence:
                        for quote in match.evidence:
                            st.code(quote)
                    else:
                        st.write("No evidence quote returned.")

            recommendation = selected_report.recommendation
            if recommendation:
                st.markdown("#### Interview plan")
                for question in recommendation.interview_questions:
                    st.write(f"- {question.question}")
                    if question.what_good_looks_like:
                        st.caption(f"What good looks like: {question.what_good_looks_like}")
                st.markdown("#### Draft - must be reviewed by a human before sending")
                st.write(recommendation.candidate_feedback or "No draft feedback returned.")

        st.subheader("Comparison")
        comparison_candidates = sorted(
            filtered_rows, key=lambda item: -item[1].match_score
        )
        top_n = st.number_input(
            "Top candidates to compare",
            min_value=1,
            max_value=max(1, len(comparison_candidates)),
            value=min(5, len(comparison_candidates)),
            step=1,
        )
        comparison_candidates = comparison_candidates[:int(top_n)]
        comparison_data = []
        for requirement in stored_job.requirements:
            row = {
                "Requirement": f"{requirement.id} ({requirement.type}): {requirement.text}"
            }
            for name, report in comparison_candidates:
                match = next(
                    item for item in report.matches
                    if item.requirement_id == requirement.id
                )
                row[name] = f"{match.score}/4" + (
                    " - MISSING" if requirement.type == "must" and match.score == 0 else ""
                )
            comparison_data.append(row)
        st.dataframe(comparison_data, use_container_width=True, hide_index=True)

        st.subheader("Downloads")
        generated_at = datetime.now().astimezone().isoformat()
        ranking_csv_data = ranking_csv(
            filtered_rows, stored_job, llm.name, prompts.PROMPT_VERSION, generated_at
        )
        ranking_excel_data = ranking_excel(
            filtered_rows, stored_job, llm.name, prompts.PROMPT_VERSION, generated_at
        )
        comparison_csv_data = comparison_csv(
            stored_job, comparison_candidates, llm.name, prompts.PROMPT_VERSION, generated_at
        )
        st.download_button(
            "Download ranking CSV",
            ranking_csv_data,
            "resume-ranking.csv",
            "text/csv",
        )
        st.download_button(
            "Download ranking Excel",
            ranking_excel_data,
            "resume-ranking.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "Download comparison CSV",
            comparison_csv_data,
            "resume-comparison.csv",
            "text/csv",
        )
        st.download_button(
            "Download all candidates Markdown",
            combined_markdown(
                filtered_rows,
                stored_job,
                llm.name,
                prompts.PROMPT_VERSION,
                generated_at,
            ),
            "resume-reports.md",
            "text/markdown",
        )
        for name, report in filtered_rows:
            safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in name)
            st.download_button(
                f"Download Markdown: {name}",
                candidate_markdown(
                    name,
                    report,
                    stored_job,
                    llm.name,
                    prompts.PROMPT_VERSION,
                    generated_at,
                ),
                f"{safe_name}-report.md",
                "text/markdown",
                key=f"download-{name}",
            )

st.caption(f"Dashboard loaded {datetime.now().astimezone().isoformat(timespec='seconds')}.")
