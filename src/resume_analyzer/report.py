from __future__ import annotations

from .models import JobSpec, Report

ICON = {"Strong Advance": "[++]", "Advance": "[+]", "Hold": "[~]", "Decline": "[-]"}


def render_markdown(r: Report, job: JobSpec) -> str:
    req = {x.id: x for x in job.requirements}
    out = [f"# {r.candidate_ref} - {r.job_title}",
           f"**{ICON[r.tier]} {r.tier}** | match score **{r.match_score}/100**"
           + (" | **HUMAN REVIEW REQUIRED**" if r.needs_human_review else ""), "",
           ]
    if r.recommendation:
        out += [f"> {r.recommendation.headline}", "", r.recommendation.rationale, ""]
    if r.review_reasons:
        out += ["## Review flags"] + [f"- {x}" for x in r.review_reasons] + [""]
    if r.profile.integrity_flags:
        out += ["## Integrity flags"] + [f"- `{f.type}`: {f.detail}" for f in r.profile.integrity_flags] + [""]
    out += ["## Requirement breakdown", "| ID | Type | Requirement | Score | Conf. | Evidence |", "|---|---|---|---|---|---|"]
    for m in r.matches:
        q = req[m.requirement_id]
        ev = (m.evidence[0][:70] + "...") if m.evidence and len(m.evidence[0]) > 70 else (m.evidence[0] if m.evidence else "-")
        out.append(f"| {q.id} | {q.type} | {q.text} | {m.score}/4{'' if m.verified else ' *'} | {m.confidence} | {ev} |")
    if r.recommendation:
        out += ["", "## Interview plan"]
        for i, q in enumerate(r.recommendation.interview_questions, 1):
            out.append(f"{i}. {q.question}  \n   _Good looks like:_ {q.what_good_looks_like}")
        out += ["", "## Candidate feedback (draft)", r.recommendation.candidate_feedback]
    else:
        out += ["", "_Recommendation not requested._"]
    return "\n".join(out)


def render_ranking(rows: list[tuple[str, Report]]) -> str:
    rows = sorted(rows, key=lambda x: -x[1].match_score)
    out = ["| Rank | File | Score | Tier | Review |", "|---|---|---|---|---|"]
    for i, (name, r) in enumerate(rows, 1):
        out.append(f"| {i} | {name} | {r.match_score} | {r.tier} | {'yes' if r.needs_human_review else ''} |")
    return "\n".join(out)
