"""Deterministic policy: evidence verification, arithmetic and tier decisions live in code, not in the LLM."""
from __future__ import annotations

import re

from .models import JobSpec, RequirementMatch

WEIGHTS = {"must": 3, "nice": 1}
STRONG_ADVANCE, ADVANCE, HOLD = 75.0, 60.0, 40.0
BOUNDARY_MARGIN = 3.0   


def _norm(s: str) -> str:
    s = s.lower().replace("\u2019", "'").replace("\u2018", "'")
    return " ".join(re.sub(r"[^a-z0-9%+#./' ]+", " ", s).split())


def evidence_is_grounded(quote: str, resume: str) -> bool:
    """A quote is grounded if every '...'-separated fragment appears verbatim (normalised) in the resume."""
    haystack = _norm(resume)
    parts = [p for p in re.split(r"\.\.\.|\u2026", quote) if len(_norm(p)) >= 4]
    return bool(parts) and all(_norm(p) in haystack for p in parts)


def reconcile(job: JobSpec, matches: list[RequirementMatch], resume: str) -> list[RequirementMatch]:
    """One verified match per requirement, in job order. Unsupported claims are capped, not trusted."""
    by_id: dict[str, RequirementMatch] = {}
    for m in matches:
        by_id.setdefault(m.requirement_id, m)
    out: list[RequirementMatch] = []
    for req in job.requirements:
        m = by_id.get(req.id)
        if m is None:
            out.append(RequirementMatch(
                requirement_id=req.id, score=0, confidence="low", verified=False,
                reasoning="No assessment returned for this requirement; needs human check."))
            continue
        good = [q for q in m.evidence if evidence_is_grounded(q, resume)]
        m = m.model_copy(update={"evidence": good})
        if m.score > 1 and not good:
            m.score, m.verified, m.confidence = 1, False, "low"
            m.reasoning = (m.reasoning + " [auto-capped: no verifiable evidence quote]").strip()
        out.append(m)
    return out


def compute(job: JobSpec, matches: list[RequirementMatch], has_integrity_flag: bool) -> dict:
    by_id = {m.requirement_id: m for m in matches}
    total = sum(WEIGHTS[r.type] for r in job.requirements)
    got = sum(WEIGHTS[r.type] * by_id[r.id].score / 4 for r in job.requirements)
    score = round(100 * got / total, 1) if total else 0.0

    musts = [(r, by_id[r.id]) for r in job.requirements if r.type == "must"]
    knockouts = [r.text for r, m in musts if m.score == 0]
    min_must = min((m.score for _, m in musts), default=4)

    if score >= STRONG_ADVANCE and min_must >= 2:
        tier = "Strong Advance"
    elif score >= ADVANCE and not knockouts:
        tier = "Advance"
    elif score >= HOLD:
        tier = "Hold"
    else:
        tier = "Decline"

    reasons: list[str] = []
    if has_integrity_flag:
        reasons.append("Integrity flag raised (e.g. instructions aimed at the screening system).")
    low = sum(1 for m in matches if m.confidence == "low" or not m.verified)
    if matches and low / len(matches) >= 0.4:
        reasons.append("Many assessments are low-confidence or unverified.")
    for edge in (STRONG_ADVANCE, ADVANCE, HOLD):
        if abs(score - edge) <= BOUNDARY_MARGIN:
            reasons.append(f"Score is within {BOUNDARY_MARGIN:g} points of the {edge:g} tier boundary.")
            break
    if tier in ("Strong Advance", "Advance") and has_integrity_flag:
        tier = "Hold"  # never auto-advance a flagged resume
        reasons.append("Tier capped at Hold until a human clears the integrity flag.")
    return {"score": score, "tier": tier, "knockouts": knockouts,
            "needs_review": bool(reasons), "reasons": reasons}
