"""run the eval set against the live llm and score keyword hit rate.

usage:
    python -m eval.run_eval                       # run all cases, write eval/results.json
    python -m eval.run_eval --case db_timeout     # run one case

scoring:
    keyword_hit  = expected_keywords matched in analysis (case-insensitive substring) / len(expected_keywords)
    anti_clean   = anti_keywords absent in analysis / len(anti_keywords)
    case_score   = 0.7 * keyword_hit + 0.3 * anti_clean

aggregate score = mean(case_score). this is a coarse signal, not a benchmark — see eval/README.md.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from backend import llm
from backend.config import WINDOW_SECONDS
from backend.correlator import correlate, format_window

DATASET = Path(__file__).parent / "dataset.json"
RESULTS = Path(__file__).parent / "results.json"


def score_case(analysis: str, expected: list[str], anti: list[str]) -> dict:
    text = analysis.lower()
    hit = [k for k in expected if k.lower() in text]
    clean = [k for k in anti if k.lower() not in text]
    keyword_hit = len(hit) / max(len(expected), 1)
    anti_clean = len(clean) / max(len(anti), 1)
    case_score = 0.7 * keyword_hit + 0.3 * anti_clean
    return {
        "keyword_hit": round(keyword_hit, 3),
        "anti_clean": round(anti_clean, 3),
        "case_score": round(case_score, 3),
        "missed_keywords": [k for k in expected if k.lower() not in text],
        "anti_violations": [k for k in anti if k.lower() in text],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--case", help="run only a single case by id")
    args = p.parse_args()

    cases = json.loads(DATASET.read_text())
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"no such case: {args.case}", file=sys.stderr)
            return 2

    out = []
    for c in cases:
        bundles = correlate(c["logs"], window_seconds=WINDOW_SECONDS)
        # the dataset has one trace per case
        trace_id, bundle = next(iter(bundles.items()))
        text = format_window(bundle)
        t0 = time.perf_counter()
        try:
            analysis, model = llm.analyze(text, WINDOW_SECONDS)
            err = None
        except Exception as e:
            analysis, model, err = "", "", str(e)
        latency_s = round(time.perf_counter() - t0, 3)

        scored = score_case(analysis, c["expected_keywords"], c["anti_keywords"])
        result = {
            "id": c["id"],
            "trace_id": trace_id,
            "model": model,
            "latency_s": latency_s,
            "analysis": analysis,
            "error": err,
            **scored,
        }
        out.append(result)
        marker = "✓" if scored["case_score"] >= 0.7 else "✗"
        print(f"{marker} {c['id']:<24} score={scored['case_score']:.2f} latency={latency_s}s")
        if err:
            print(f"    error: {err}")

    succeeded = [r for r in out if r["error"] is None]
    aggregate = {
        "n_cases": len(out),
        "n_succeeded": len(succeeded),
        "mean_score": round(statistics.fmean([r["case_score"] for r in succeeded]), 3) if succeeded else 0.0,
        "mean_latency_s": round(statistics.fmean([r["latency_s"] for r in succeeded]), 3) if succeeded else 0.0,
    }
    payload = {"aggregate": aggregate, "cases": out}
    RESULTS.write_text(json.dumps(payload, indent=2))
    print()
    print(f"aggregate: {aggregate}")
    print(f"wrote {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
