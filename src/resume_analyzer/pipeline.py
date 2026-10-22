"""Orchestrates: sanitize -> extract -> parse JD -> score -> verify -> policy -> recommend."""
from __future__ import annotations

import hashlib
import json

from . import __version__, prompts, scoring
from . import cache
from .llm import LLM
from .models import (Evaluation, IntegrityFlag, JobSpec, Recommendation, Report, ResumeProfile)
from .sanitize import sanitize


def _normalize_job(spec: JobSpec) -> JobSpec:
    m = n = 0
    for r in spec.requirements:
        if r.type == "must":
            m += 1
            r.id = f"M{m}"
        else:
            n += 1
            r.id = f"N{n}"
    if not spec.requirements:
        raise ValueError("Job description produced no requirements.")
    return spec


def _merge_flags(*groups: list[IntegrityFlag]) -> list[IntegrityFlag]:
    seen, out = set(), []
    for g in groups:
        for f in g:
            if f.type not in seen:
                seen.add(f.type)
                out.append(f)
    return out


class Analyzer:
    def __init__(self, llm: LLM):
        self.llm = llm
        self._job_ids: dict[str, str] = {}

    def _job_fingerprint(self, job: JobSpec) -> str:
        return json.dumps(job.model_dump(), sort_keys=True)

    def parse_job(self, job_text: str) -> JobSpec:
        clean, _ = sanitize(job_text, redact=False)
        cached = cache.get_job(clean)
        if cached and cached["prompt_version"] == prompts.PROMPT_VERSION:
            self.llm.usage.record_cache_hit("parse_jd", self.llm.name)
            spec = _normalize_job(JobSpec.model_validate(json.loads(cached["parsed_json"])))
            self._job_ids[self._job_fingerprint(spec)] = cached["job_id"]
            return spec
        system, user = prompts.build("02_parse_jd", job=clean)
        spec = _normalize_job(self.llm.json_call(
            "parse_jd", system, user, JobSpec, max_tokens=2000))
        cached_job_id = cache.put_job(clean, spec.model_dump(), prompts.PROMPT_VERSION)
        self._job_ids[self._job_fingerprint(spec)] = cached_job_id
        return spec

    def analyze(self, resume_text: str, job: JobSpec, with_recommendation: bool = False) -> Report:
        clean, pre_flags = sanitize(resume_text)
        ref = "CAND-" + hashlib.sha256(clean.encode()).hexdigest()[:8]
        cached_job_id = self._job_ids.get(
            self._job_fingerprint(job),
            cache.job_id(self._job_fingerprint(job)),
        )
        key = cache.result_key(clean, cached_job_id, prompts.PROMPT_VERSION, self.llm.name)
        cached = cache.get_result(key)
        if cached:
            self.llm.usage.record_cache_hit("analyze", self.llm.name)
            report = Report.model_validate(json.loads(cached["report_json"]))
            report.meta["cached"] = True
            if with_recommendation and report.recommendation is None:
                return self.recommend(report, job)
            return report

        system, user = prompts.build("01_extract_resume", resume=clean)
        profile = self.llm.json_call(
            "extract", system, user, ResumeProfile, max_tokens=2500)
        profile.integrity_flags = _merge_flags(pre_flags, profile.integrity_flags)

        system, user = prompts.build(
            "03_score_match", job_title=job.title,
            requirements=json.dumps([r.model_dump() for r in job.requirements]),
            profile=profile.model_dump_json(exclude={"integrity_flags"}), resume=clean)
        ev = self.llm.json_call("score", system, user, Evaluation, max_tokens=4000)

        matches = scoring.reconcile(job, ev.matches, clean)
        result = scoring.compute(job, matches, has_integrity_flag=bool(profile.integrity_flags))

        report = Report(
            candidate_ref=ref, job_title=job.title, match_score=result["score"], tier=result["tier"],
            knockouts=result["knockouts"], needs_human_review=result["needs_review"],
            review_reasons=result["reasons"], profile=profile, matches=matches,
            strengths=ev.strengths, gaps=ev.gaps, verify_in_interview=ev.verify_in_interview,
            recommendation=None,
            meta={"model": self.llm.name, "prompt_version": prompts.PROMPT_VERSION,
                  "app_version": __version__, "cached": False, "cache_key": key})
        cache.put_result(key, report.model_dump())
        if with_recommendation:
            return self.recommend(report, job)
        return report

    def recommend(self, report: Report, job: JobSpec) -> Report:
        if report.recommendation is not None:
            return report
        analysis = {
            "job_title": job.title, "tier": report.tier, "match_score": report.match_score,
            "requirements_with_scores": [
                {"id": r.id, "text": r.text, "type": r.type,
                 "score": m.score, "confidence": m.confidence}
                for r, m in zip(job.requirements, report.matches)],
            "strengths": report.strengths, "gaps": report.gaps,
            "verify_in_interview": report.verify_in_interview,
            "needs_human_review": report.needs_human_review,
            "review_reasons": report.review_reasons,
        }
        system, user = prompts.build("04_recommend", analysis=json.dumps(analysis))
        report.recommendation = self.llm.json_call(
            "recommend", system, user, Recommendation, max_tokens=2000)
        report.meta["cached"] = False
        if report.meta.get("cache_key"):
            cache.put_result(report.meta["cache_key"], report.model_dump())
        return report
