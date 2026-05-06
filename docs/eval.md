# eval

50 hand-crafted log bundles in `eval/dataset.json`, each with:

- `logs` — a small bundle of synthetic log lines (3–4 typical) for the case
- `expected_keywords` — vocabulary that should appear in a correct answer
- `anti_keywords` — vocabulary that signals a wrong direction
- `gold` — a 1–2 sentence reference answer written by a senior engineer

this is small enough to be honest about. 50 cases gives a usable signal for a/b prompt comparison and regression. it is not a published-paper benchmark.

## scoring modes

each case is scored three ways (`--scorer`):

- `keyword` — `0.7 * keyword_hit + 0.3 * anti_clean`. cheap, no embedding cost.
- `embedding` — `cosine(embed(analysis), embed(gold))` using azure openai `text-embedding-3-small`. embeddings are deterministic and cached to `eval/.embed_cache.json` so gold answers are billed once.
- `both` (default) — `0.5 * keyword + 0.5 * embedding`. catches both vocabulary and semantic mismatches.

a case is "passing" if `case_score >= 0.7`. embedding similarity is a stronger signal than keyword match but is not ground truth — it rewards answers that *sound* like the gold answer, not necessarily ones that are operationally correct.

## prompt versions

prompts live in `backend/prompts/v{N}.py` and are append-only. `PROMPT_VERSION` env switches the live one.

- `v1` — original. `root_cause`, `next_step`, `evidence` fields.
- `v2` — adds `category` and `confidence`.
- `v3` — same fields as v2 but the model is required to return strict json (`response_format=json_object`). parsed fields land in dedicated columns and are scored by name in eval.

## a/b compare

```bash
python -m eval.run_eval --version v2
python -m eval.run_eval --version v3
python -m eval.compare eval/results-v2.json eval/results-v3.json
```

the compare output has up/down arrows for cases where one version scored ≥0.05 higher than the other, plus a per-version aggregate at the bottom.

## multi-seed agreement

```bash
python -m eval.run_eval --runs 3 --temperature 0.7
```

each case runs N times with seeds 1..N. per case we record:

- `agreement_pairwise_cos` — mean cosine across pairs of run embeddings.
- `agreement_category` — fraction of run pairs that picked the same `category`.

high pairwise cos + high category agreement = consistent under sampling. high cos but low category agreement = the model wanders semantically while keeping vocabulary stable.

cost: `--runs N` multiplies the llm bill by N. embeddings for identical run outputs hit the local cache.

## what's still missing (deliberate, not pretending)

- structured outputs scored against named fields (`root_cause`, `category`) instead of free text. v3 prompt populates them; the scorer doesn't yet use them directly.
- a published prompt-comparison report would need a larger labeled set + statistical significance testing.
