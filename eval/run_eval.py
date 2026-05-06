"""run the eval set against the live llm and score per case.

usage:
    python -m eval.run_eval                                  # all cases, current PROMPT_VERSION
    python -m eval.run_eval --case db_timeout                # one case
    python -m eval.run_eval --version v1                     # pin a specific prompt version
    python -m eval.run_eval --scorer keyword                 # legacy keyword-only
    python -m eval.run_eval --scorer embedding               # cosine(embed(answer), embed(gold))
    python -m eval.run_eval --scorer both                    # default. blended case_score.

scoring (per case):
    keyword_hit  = expected_keywords found in analysis / len(expected_keywords)
    anti_clean   = anti_keywords NOT found / len(anti_keywords)
    keyword_score = 0.7*keyword_hit + 0.3*anti_clean
    embed_score   = cosine(embed(analysis), embed(gold))
    case_score (both) = 0.5 * keyword_score + 0.5 * embed_score

aggregate is the mean of case_score across non-error cases. it's coarse — see eval/README.md.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from backend import embeddings, llm
from backend.config import PROMPT_VERSION, WINDOW_SECONDS
from backend.correlator import correlate, format_window

DATASET = Path(__file__).parent / "dataset.json"
EMBED_CACHE = Path(__file__).parent / ".embed_cache.json"


def score_keywords(analysis: str, expected: list[str], anti: list[str]) -> dict:
    text = analysis.lower()
    hit = [k for k in expected if k.lower() in text]
    clean = [k for k in anti if k.lower() not in text]
    keyword_hit = len(hit) / max(len(expected), 1)
    anti_clean = len(clean) / max(len(anti), 1)
    keyword_score = 0.7 * keyword_hit + 0.3 * anti_clean
    return {
        "keyword_hit": round(keyword_hit, 3),
        "anti_clean": round(anti_clean, 3),
        "keyword_score": round(keyword_score, 3),
        "missed_keywords": [k for k in expected if k.lower() not in text],
        "anti_violations": [k for k in anti if k.lower() in text],
    }


def _load_embed_cache() -> dict[str, list[float]]:
    if EMBED_CACHE.exists():
        try:
            return json.loads(EMBED_CACHE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_embed_cache(cache: dict[str, list[float]]) -> None:
    EMBED_CACHE.write_text(json.dumps(cache))


def score_embedding(analysis: str, gold: str, cache: dict[str, list[float]]) -> float:
    if not analysis or not gold:
        return 0.0
    a = cache.get(analysis)
    if a is None:
        a = embeddings.embed(analysis)
        cache[analysis] = a
    b = cache.get(gold)
    if b is None:
        b = embeddings.embed(gold)
        cache[gold] = b
    return embeddings.cosine(a, b)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--case", help="run only a single case by id")
    p.add_argument("--version", default=PROMPT_VERSION, help="prompt version to evaluate (default: PROMPT_VERSION env)")
    p.add_argument("--output", help="results filename in eval/ (default: results-{version}.json)")
    p.add_argument(
        "--scorer",
        choices=["keyword", "embedding", "both"],
        default="both",
        help="scoring mode (default: both)",
    )
    args = p.parse_args()

    cases = json.loads(DATASET.read_text())
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"no such case: {args.case}", file=sys.stderr)
            return 2

    results_path = Path(__file__).parent / (args.output or f"results-{args.version}.json")
    embed_cache = _load_embed_cache() if args.scorer in {"embedding", "both"} else {}

    out = []
    for c in cases:
        bundles = correlate(c["logs"], window_seconds=WINDOW_SECONDS)
        trace_id, bundle = next(iter(bundles.items()))
        text = format_window(bundle)
        t0 = time.perf_counter()
        try:
            res = llm.analyze(text, WINDOW_SECONDS, version=args.version)
            analysis, model, used_version = res.raw_text, res.model, res.prompt_version
            category, confidence = res.category, res.confidence
            err = None
        except Exception as e:
            analysis, model, used_version = "", "", args.version
            category, confidence = None, None
            err = str(e)
        latency_s = round(time.perf_counter() - t0, 3)

        kw = score_keywords(analysis, c["expected_keywords"], c["anti_keywords"])
        emb_score: float | None = None
        if args.scorer in {"embedding", "both"} and not err:
            try:
                emb_score = round(score_embedding(analysis, c.get("gold", ""), embed_cache), 3)
            except Exception as e:
                print(f"    embedding scoring failed for {c['id']}: {e}", file=sys.stderr)

        if args.scorer == "keyword":
            case_score = kw["keyword_score"]
        elif args.scorer == "embedding":
            case_score = emb_score if emb_score is not None else 0.0
        else:  # both
            case_score = round(0.5 * kw["keyword_score"] + 0.5 * (emb_score or 0.0), 3) if emb_score is not None else kw["keyword_score"]

        result = {
            "id": c["id"],
            "trace_id": trace_id,
            "model": model,
            "prompt_version": used_version,
            "category": category,
            "confidence": confidence,
            "latency_s": latency_s,
            "analysis": analysis,
            "gold": c.get("gold"),
            "embedding_score": emb_score,
            "case_score": case_score,
            "error": err,
            **kw,
        }
        out.append(result)
        marker = "✓" if case_score >= 0.7 else "✗"
        emb_part = f" emb={emb_score:.2f}" if emb_score is not None else ""
        print(f"{marker} {c['id']:<28} score={case_score:.2f}{emb_part} latency={latency_s}s")
        if err:
            print(f"    error: {err}")

    if embed_cache:
        _save_embed_cache(embed_cache)

    succeeded = [r for r in out if r["error"] is None]
    aggregate = {
        "prompt_version": args.version,
        "scorer": args.scorer,
        "n_cases": len(out),
        "n_succeeded": len(succeeded),
        "n_passing": sum(1 for r in succeeded if r["case_score"] >= 0.7),
        "mean_score": round(statistics.fmean([r["case_score"] for r in succeeded]), 3) if succeeded else 0.0,
        "mean_keyword_score": round(statistics.fmean([r["keyword_score"] for r in succeeded]), 3) if succeeded else 0.0,
        "mean_embedding_score": (
            round(
                statistics.fmean([r["embedding_score"] for r in succeeded if r["embedding_score"] is not None]), 3
            )
            if any(r["embedding_score"] is not None for r in succeeded)
            else None
        ),
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
