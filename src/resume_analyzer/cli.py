from __future__ import annotations

import argparse
import json
from pathlib import Path

from .llm import get_llm
from .batch import run_batch
from .documents import SUPPORTED_SUFFIXES, read_document
from .pipeline import Analyzer
from .report import render_markdown, render_ranking


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="resume_analyzer", description="Resume analysis & recommendation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyse one resume against a job")
    a.add_argument("--resume", required=True)
    a.add_argument("--job", required=True)
    a.add_argument("--json", action="store_true", help="print raw JSON report")
    a.add_argument("--no-cache", action="store_true", help="bypass reading cached results")
    r = sub.add_parser("rank", help="rank every .txt resume in a folder against a job")
    r.add_argument("--resumes", required=True)
    r.add_argument("--job", required=True)
    r.add_argument("--with-recommendations", action="store_true")
    r.add_argument("--no-cache", action="store_true", help="bypass reading cached results")
    args = ap.parse_args(argv)

    if args.no_cache:
        import os
        os.environ["RA_CACHE_DISABLED"] = "1"

    analyzer = Analyzer(get_llm())
    job = analyzer.parse_job(read_document(args.job))
    if args.cmd == "analyze":
        rep = analyzer.analyze(read_document(args.resume), job, with_recommendation=True)
        print(rep.model_dump_json(indent=2) if args.json else render_markdown(rep, job))
    else:
        paths = sorted(
            path for path in Path(args.resumes).iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        )
        batch_results = run_batch(
            paths, job, analyzer,
            with_recommendations=args.with_recommendations,
        )
        rows = [
            (r["name"], r["report"])
            for r in batch_results
            if r.get("report") is not None
        ]
        print(render_ranking(rows))
        print("\n| File | Status |")
        print("|---|---|")
        for result in batch_results:
            print(f"| {result['name']} | {result['status']} |")
        print("\nUsage:", json.dumps(analyzer.llm.usage.summary(), sort_keys=True))
    return 0
