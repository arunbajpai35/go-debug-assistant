"""run the eval set against the live llm and score per case.

usage:
    python -m eval.run_eval                                  # all cases, current PROMPT_VERSION
    python -m eval.run_eval --case db_timeout                # one case
    python -m eval.run_eval --version v1                     # pin a specific prompt version
    python -m eval.run_eval --scorer keyword                 # legacy keyword-only
    python -m eval.run_eval --scorer embedding               # cosine(embed(answer), embed(gold))
    python -m eval.run_eval --scorer both                    # default. blended case_score.
    python -m eval.run_eval --runs 3 --temperature 0.7       # multi-seed agreement; first run
                                                             # is the scored one, all runs combined
                                                             # produce per-case agreement metrics

scoring (per case):
    keyword_hit  = expected_keywords found in analysis / len(expected_keywords)
    anti_clean   = anti_keywords NOT found / len(anti_keywords)
    keyword_score = 0.7*keyword_hit + 0.3*anti_clean
    embed_score   = cosine(embed(analysis), embed(gold))
    case_score (both) = 0.5 * keyword_score + 0.5 * embed_score

agreement (when --runs > 1):
    pairwise_cos      = mean cosine across all pairs of run embeddings for the case
    category_agreement = fraction of run pairs where both runs picked the same category

cost note: --runs N multiplies llm cost by N. each run uses seed=i so they're reproducible.
the embedding cache covers analysis text identity, so identical outputs across runs are free
to score.
"""
import argparse
import asyncio
import itertools
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


def _embed_cached(text: str, cache: dict[str, list[float]]) -> list[float]:
    v = cache.get(text)
    if v is None:
        v = embeddings.embed(text)
        cache[text] = v
    return v


def score_embedding(analysis: str, gold: str, cache: dict[str, list[float]]) -> float:
    if not analysis or not gold:
        return 0.0
    return embeddings.cosine(_embed_cached(analysis, cache), _embed_cached(gold, cache))


def pairwise_agreement(texts: list[str], categories: list[str | None], cache: dict[str, list[float]]) -> dict:
    if len(texts) < 2:
        return {"pairwise_cos": None, "category_agreement": None}
    pairs = list(itertools.combinations(range(len(texts)), 2))
    sims: list[float] = []
    cat_match: list[int] = []
    for i, j in pairs:
        a, b = texts[i], texts[j]
        if a and b:
            sims.append(embeddings.cosine(_embed_cached(a, cache), _embed_cached(b, cache)))
        ci, cj = categories[i], categories[j]
        if ci is not None and cj is not None:
            cat_match.append(1 if ci == cj else 0)
    return {
        "pairwise_cos": round(statistics.fmean(sims), 3) if sims else None,
        "category_agreement": round(statistics.fmean(cat_match), 3) if cat_match else None,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--case", help="run only a single case by id")
    p.add_argument("--version", default=PROMPT_VERSION, help="prompt version to evaluate")
    p.add_argument("--output", help="results filename in eval/ (default: results-{version}.json)")
    p.add_argument(
        "--scorer",
        choices=["keyword", "embedding", "both"],
        default="both",
        help="scoring mode (default: both)",
    )
    p.add_argument("--runs", type=int, default=1, help="number of llm runs per case for agreement (default 1, no agreement)")
    p.add_argument("--temperature", type=float, default=0.2, help="llm sampling temperature (default 0.2)")
    args = p.parse_args()

    cases = json.loads(DATASET.read_text())
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"no such case: {args.case}", file=sys.stderr)
            return 2

    results_path = Path(__file__).parent / (args.output or f"results-{args.version}.json")
    needs_embeds = args.scorer in {"embedding", "both"} or args.runs > 1
    embed_cache = _load_embed_cache() if needs_embeds else {}

    out = []
    for c in cases:
        bundles = correlate(c["logs"], window_seconds=WINDOW_SECONDS)
        trace_id, bundle = next(iter(bundles.items()))
        text = format_window(bundle)

        run_outputs: list[str] = []
        run_categories: list[str | None] = []
        run_latencies: list[float] = []
        first_err: str | None = None
        primary_model = ""
        primary_used_version = args.version
        primary_confidence: str | None = None

        for run_idx in range(args.runs):
            t0 = time.perf_counter()
            try:
                res = asyncio.run(
                    llm.analyze(
                        text,
                        WINDOW_SECONDS,
                        version=args.version,
                        seed=run_idx + 1,
                        temperature=args.temperature,
                    )
                )
                run_outputs.append(res.raw_text)
                run_categories.append(res.category)
                if run_idx == 0:
                    primary_model = res.model
                    primary_used_version = res.prompt_version
                    primary_confidence = res.confidence
            except Exception as e:
                first_err = first_err or str(e)
                run_outputs.append("")
                run_categories.append(None)
            run_latencies.append(round(time.perf_counter() - t0, 3))

        analysis = run_outputs[0]
        category = run_categories[0]
        latency_s = run_latencies[0]
        err = first_err if not analysis else None

        kw = score_keywords(analysis, c["expected_keywords"], c["anti_keywords"])
        emb_score: float | None = None
        if args.scorer in {"embedding", "both"} and not err:
            try:
                emb_score = round(score_embedding(analysis, c.get("gold", ""), embed_cache), 3)
            except Exception as e:
                print(f"    embedding scoring failed for {c['id']}: {e}", file=sys.stderr)

        agreement = pairwise_agreement(run_outputs, run_categories, embed_cache) if args.runs > 1 else {
            "pairwise_cos": None,
            "category_agreement": None,
        }

        if args.scorer == "keyword":
            case_score = kw["keyword_score"]
        elif args.scorer == "embedding":
            case_score = emb_score if emb_score is not None else 0.0
        else:
            case_score = (
                round(0.5 * kw["keyword_score"] + 0.5 * (emb_score or 0.0), 3)
                if emb_score is not None
                else kw["keyword_score"]
            )

        result = {
            "id": c["id"],
            "trace_id": trace_id,
            "model": primary_model,
            "prompt_version": primary_used_version,
            "category": category,
            "confidence": primary_confidence,
            "latency_s": latency_s,
            "analysis": analysis,
            "gold": c.get("gold"),
            "embedding_score": emb_score,
            "case_score": case_score,
            "runs": args.runs,
            "run_latencies": run_latencies,
            "agreement_pairwise_cos": agreement["pairwise_cos"],
            "agreement_category": agreement["category_agreement"],
            "error": err,
            **kw,
        }
        out.append(result)
        marker = "✓" if case_score >= 0.7 else "✗"
        emb_part = f" emb={emb_score:.2f}" if emb_score is not None else ""
        ag_part = (
            f" agreement={agreement['pairwise_cos']:.2f}/{agreement['category_agreement']:.2f}"
            if agreement["pairwise_cos"] is not None and agreement["category_agreement"] is not None
            else ""
        )
        print(f"{marker} {c['id']:<28} score={case_score:.2f}{emb_part}{ag_part} latency={latency_s}s")
        if err:
            print(f"    error: {err}")

    if embed_cache:
        _save_embed_cache(embed_cache)

    succeeded = [r for r in out if r["error"] is None]
    agreement_cos = [r["agreement_pairwise_cos"] for r in succeeded if r["agreement_pairwise_cos"] is not None]
    agreement_cat = [r["agreement_category"] for r in succeeded if r["agreement_category"] is not None]
    aggregate = {
        "prompt_version": args.version,
        "scorer": args.scorer,
        "runs": args.runs,
        "temperature": args.temperature,
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
        "mean_agreement_pairwise_cos": round(statistics.fmean(agreement_cos), 3) if agreement_cos else None,
        "mean_agreement_category": round(statistics.fmean(agreement_cat), 3) if agreement_cat else None,
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
