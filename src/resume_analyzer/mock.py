"""Offline stand-in for the model so the whole pipeline, tests and eval harness run without an API key.
It is a crude keyword heuristic, NOT a measure of prompt quality. Real accuracy comes from the real model."""
from __future__ import annotations

import json
import re

from .llm import LLM

STOP = {"experience", "with", "using", "and", "the", "years", "year", "knowledge", "strong", "good",
        "exposure", "working", "ability", "skills", "proficiency", "hands", "familiarity", "of", "in",
        "or", "to", "a", "an", "for", "domain", "plus"}
VOCAB = ["Python", "FastAPI", "Flask", "Django", "PostgreSQL", "MySQL", "SQL", "Redis", "Docker",
         "Kubernetes", "AWS", "GCP", "Azure", "Celery", "RabbitMQ", "Kafka", "pytest", "pandas",
         "Excel", "JavaScript", "HTML", "CSS", "React", "Git"]
BIAS_WORDS = ["rockstar", "ninja", "young", "energetic", "digital native", "native speaker", "recent graduate"]


def _tag(s: str, name: str) -> str:
    m = re.search(rf"<{name}>\s*(.*?)\s*</{name}>", s, re.S)
    return m.group(1) if m else ""


def _section(text: str, header: str) -> str:
    lines, out, on = text.splitlines(), [], False
    for ln in lines:
        if ln.strip().upper() == header:
            on = True
            continue
        if on and re.fullmatch(r"[A-Z &]{4,}", ln.strip()):
            break
        if on:
            out.append(ln)
    return "\n".join(out)


def _years(text: str) -> float:
    total = 0
    for s, e in re.findall(r"(\d{4})\s*[-\u2013]\s*(\d{4}|Present)", _section(text, "EXPERIENCE")):
        total += max(0, (2026 if e == "Present" else int(e)) - int(s))
    return float(total)


def _stem(tok: str) -> str:
    return tok.rstrip("s")[:5]


class MockLLM(LLM):
    name = "mock-heuristic"

    def complete(self, task, system, messages, max_tokens=4000, temperature=0.0,
                 response_schema=None):
        user = messages[0]["content"]
        return json.dumps(getattr(self, f"_{task}")(user))

    # --- tasks -------------------------------------------------------------
    def _parse_jd(self, user):
        jd = _tag(user, "job_description")
        title = (re.search(r"Job Title:\s*(.+)", jd) or [None, "Untitled role"])[1].strip()
        seniority = (re.search(r"Seniority:\s*(.+)", jd) or [None, "unspecified"])[1].strip()
        reqs, mode = [], None
        for ln in jd.splitlines():
            low = ln.strip().lower()
            if low.startswith("must-have") or low.startswith("requirements"):
                mode = "must"
            elif low.startswith("nice-to-have") or low.startswith("bonus"):
                mode = "nice"
            elif ln.strip().startswith("- ") and mode:
                reqs.append({"id": f"R{len(reqs) + 1}", "text": ln.strip()[2:], "type": mode,
                             "category": "skill"})
        notes = [w for w in BIAS_WORDS if w in jd.lower()]
        return {"title": title, "seniority": seniority, "requirements": reqs, "inclusivity_notes": notes}

    def _extract(self, user):
        text = _tag(user, "resume")
        roles = [{"title": m[0].strip(), "company": m[1].strip(), "start": m[2], "end": m[3]}
                 for m in re.findall(r"^([^,\n(]+),\s*([^(\n]+?)\s*\((\d{4})\s*[-\u2013]\s*(\d{4}|Present)\)",
                                     text, re.M)]
        skills = [s for s in VOCAB if re.search(rf"\b{re.escape(s)}\b", text, re.I)]
        flags = []
        if re.search(r"ignore (all |any )?(previous|prior)", text, re.I):
            flags.append({"type": "prompt_injection", "detail": "Text addressed to an AI system."})
        return {"summary": f"Candidate with {len(roles)} listed role(s) and {len(skills)} recognised skills.",
                "skills": skills, "experience": roles, "education": [], "certifications": [],
                "total_years_experience": _years(text), "integrity_flags": flags}

    def _score(self, user):
        resume = _tag(user, "resume_redacted")
        reqs = json.loads(_tag(user, "requirements"))
        years = json.loads(_tag(user, "profile")).get("total_years_experience") or 0
        low, lines = resume.lower(), resume.splitlines()
        matches = []
        for r in reqs:
            base = re.sub(r"\([^)]*\)", " ", r["text"])
            group = re.findall(r"\(([^)]*)\)", r["text"])
            toks = [t for t in re.findall(r"[a-z][a-z0-9+#]*", base.lower()) if t not in STOP and len(t) > 2]
            alts = [a.strip().lower() for g in group for a in re.split(r"[,/]", g) if a.strip()]
            hit_toks = [t for t in toks if _stem(t) in low]
            alt_hit = [a for a in alts if a in low]
            ratio = len(hit_toks) / len(toks) if toks else 0.0
            if alt_hit:
                ratio = max(ratio, 0.67)
            evid = next((ln.strip() for ln in lines if any(_stem(t) in ln.lower() for t in hit_toks)
                         or any(a in ln.lower() for a in alt_hit)), "")
            if ratio == 0:
                score = 0
            elif ratio < 0.34:
                score = 1
            elif ratio < 0.67:
                score = 2
            else:
                score = 4 if (ratio > 0.99 and re.search(r"\d", evid)) else 3
            need = re.search(r"(\d+)\+?\s*years", r["text"])
            if need and score:
                n = int(need.group(1))
                score = min(score, 1 if years < n * 0.5 else 2 if years < n else 4)
            in_skills_only = evid and evid.lower().startswith(("python,", "skills"))
            matches.append({"requirement_id": r["id"], "score": min(score, 1) if in_skills_only else score,
                            "reasoning": f"Heuristic keyword match ratio {ratio:.2f}.",
                            "evidence": [evid[:150]] if evid and score else [],
                            "confidence": "high" if score in (0, 3, 4) else "medium"})
        gaps = [r["text"] for r, m in zip(reqs, matches) if m["score"] <= 1]
        strengths = [r["text"] for r, m in zip(reqs, matches) if m["score"] >= 3][:3]
        return {"matches": matches, "strengths": strengths, "gaps": gaps, "verify_in_interview": []}

    def _recommend(self, user):
        a = json.loads(_tag(user, "analysis"))
        gaps = a.get("gaps", [])[:4] or ["depth of recent hands-on work"]
        reqs = {r["text"]: r["id"] for r in a.get("requirements_with_scores", [])}
        qs = [{"question": f"Tell me about a time you worked on: {g}. What was your role and outcome?",
               "targets_requirement_id": reqs.get(g, ""),
               "what_good_looks_like": "Specific situation, personal ownership, measurable result."}
              for g in gaps[:4]]
        return {"headline": f"{a['tier']}: score {a['match_score']}",
                "rationale": ("Mock rationale. " + " ".join(a.get("review_reasons", []))).strip(),
                "interview_questions": qs,
                "candidate_feedback": "Thank you for applying. Building hands-on depth in the listed gap areas "
                                      "would strengthen future applications.",
                "alternative_roles": [], "onboarding_risks": []}

    def _judge(self, user):
        return {k: {"score": 3, "why": "mock"} for k in ("groundedness", "actionability", "fairness", "tone")}
