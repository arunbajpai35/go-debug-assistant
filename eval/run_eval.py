"""run the eval set against the live llm and score keyword hit rate.

usage:
    python -m eval.run_eval                                  # all cases, current PROMPT_VERSION
    python -m eval.run_eval --case db_timeout                # one case
    python -m eval.run_eval --version v1                     # pin a specific prompt version
    python -m eval.run_eval --version v2 --output v2.json    # write to a custom file (good for ab)

scoring:
    keyword_hit  = expected_keywords matched in analysis (case-insensitive substring) / len(expected_keywords)
    anti_clean   = anti_keywords absent in analysis / len(anti_keywords)
    case_score   = 0.7 * keyword_hit + 0.3 * anti_clean

aggregate score = mean(case_score). coarse signal, not a benchmark — see eval/README.md.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from backend import llm
from backend.config import PROMPT_VERSION, WINDOW_SECONDS
from backend.correlator import correlate, format_window

DATASET = Path(__file__).parent / "dataset.json"


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
    p.add_argument("--version", default=PROMPT_VERSION, help="prompt version to evaluate (default: PROMPT_VERSION env)")
    p.add_argument("--output", help="results filename in eval/ (default: results-{version}.json)")
    args = p.parse_args()

    cases = json.loads(DATASET.read_text())
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"no such case: {args.case}", file=sys.stderr)
            return 2

    results_path = Path(__file__).parent / (args.output or f"results-{args.version}.json")

    out = []
    for c in cases:
        bundles = correlate(c["logs"], window_seconds=WINDOW_SECONDS)
        trace_id, bundle = next(iter(bundles.items()))
        text = format_window(bundle)
        t0 = time.perf_counter()
        try:
            res = llm.analyze(text, WINDOW_SECONDS, version=args.version)
            analysis = res.raw_text
            model = res.model
            used_version = res.prompt_version
            category = res.category
            confidence = res.confidence
            err = None
        except Exception as e:
            analysis, model, used_version = "", "", args.version
            category, confidence = None, None
            err = str(e)
        latency_s = round(time.perf_counter() - t0, 3)

        scored = score_case(analysis, c["expected_keywords"], c["anti_keywords"])
        result = {
            "id": c["id"],
            "trace_id": trace_id,
            "model": model,
            "prompt_version": used_version,
            "category": category,
            "confidence": confidence,
            "latency_s": latency_s,
            "analysis": analysis,
            "error": err,
            **scored,
        }
        out.append(result)
        marker = "✓" if scored["case_score"] >= 0.7 else "✗"
        print(f"{marker} {c['id']:<28} score={scored['case_score']:.2f} latency={latency_s}s")
        if err:
            print(f"    error: {err}")

    succeeded = [r for r in out if r["error"] is None]
    aggregate = {
        "prompt_version": args.version,
        "n_cases": len(out),
        "n_succeeded": len(succeeded),
        "n_passing": sum(1 for r in succeeded if r["case_score"] >= 0.7),
        "mean_score": round(statistics.fmean([r["case_score"] for r in succeeded]), 3) if succeeded else 0.0,
        "mean_latency_s": round(statistics.fmean([r["latency_s"] for r in succeeded]), 3) if succeeded else 0.0,
    }
    payload = {"aggregate": aggregate, "cases": out}
    results_path.write_text(json.dumps(payload, indent=2))
    print()
    print(f"aggregate: {aggregate}")
    print(f"wrote {results_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
