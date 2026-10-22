"""Evaluation harness: tier accuracy, ordering, injection resistance, evidence grounding, stability, optional LLM judge.
Usage: python eval/run_eval.py [--runs N] [--judge] [--no-cache]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resume_analyzer import prompts  # noqa: E402
from resume_analyzer.llm import get_llm  # noqa: E402
from resume_analyzer.models import ResumeProfile  # noqa: E402
from resume_analyzer.pipeline import Analyzer  # noqa: E402
from resume_analyzer.sanitize import sanitize  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1, help="repeat runs to measure tier stability")
    ap.add_argument("--judge", action="store_true", help="LLM-as-judge quality audit (real model only)")
    ap.add_argument("--no-cache", action="store_true", help="bypass reading cached results")
    args = ap.parse_args()

    # Stability runs must not reuse result-cache entries from an earlier run.
    if args.no_cache or args.runs > 1:
        import os
        os.environ["RA_CACHE_DISABLED"] = "1"

    gold = json.loads((ROOT / "eval" / "golden.json").read_text(encoding="utf-8"))
    llm = get_llm()
    az = Analyzer(llm)
    job = az.parse_job((ROOT / gold["job"]).read_text(encoding="utf-8"))
    resumes = {n: (ROOT / "data" / "resumes" / n).read_text(encoding="utf-8") for n in gold["cases"]}

    results, tiers_by_run = {}, {n: [] for n in resumes}
    for _ in range(args.runs):
        for n, text in resumes.items():
            rep = az.analyze(text, job, with_recommendation=args.judge)
            results[n] = rep
            tiers_by_run[n].append(rep.tier)

    checks: list[tuple[str, bool, str]] = []
    for n, spec in gold["cases"].items():
        r = results[n]
        checks.append((f"tier  {n}", r.tier in spec["acceptable_tiers"], f"{r.tier} ({r.match_score})"))
        if spec.get("must_flag_injection"):
            ok = any(f.type == "prompt_injection" for f in r.profile.integrity_flags) and r.needs_human_review
            checks.append((f"injection flagged  {n}", ok, "flagged+review" if ok else "NOT flagged"))
    for hi, lo in gold["ordering"]:
        ok = results[hi].match_score > results[lo].match_score
        checks.append((f"order {hi} > {lo}", ok, f"{results[hi].match_score} vs {results[lo].match_score}"))

    total_ev = sum(len(m.evidence) for r in results.values() for m in r.matches if m.score > 0)
    unverified = sum(1 for r in results.values() for m in r.matches if not m.verified)
    checks.append(("evidence grounding (no auto-capped claims)", unverified == 0, f"{unverified} capped / {total_ev} quotes"))
    if args.runs > 1:
        stable = sum(len(set(v)) == 1 for v in tiers_by_run.values()) / len(tiers_by_run)
        checks.append((f"tier stability over {args.runs} runs", stable >= 0.9, f"{stable:.0%}"))

    if args.judge:
        if llm.name == "mock-heuristic":
            print("[skip] --judge needs a real model")
        else:
            from pydantic import BaseModel
            class J(BaseModel):
                groundedness: dict; actionability: dict; fairness: dict; tone: dict
            for n, r in results.items():
                clean, _ = sanitize(resumes[n])
                s, u = prompts.build("05_judge_eval", resume=clean, report=r.recommendation.model_dump_json())
                j = llm.json_call("judge", s, u, J)
                low = {k: v["score"] for k, v in j.model_dump().items() if v["score"] < 4}
                checks.append((f"judge {n}", not low, str(low or "all >= 4")))

    width = max(len(c[0]) for c in checks)
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")
    passed = sum(ok for _, ok, _ in checks)
    print(f"\n{passed}/{len(checks)} checks passed  (model: {llm.name}, prompts v{prompts.PROMPT_VERSION})")
    print(f"Usage: {json.dumps(llm.usage.summary(), sort_keys=True)}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
