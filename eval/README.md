# eval

50 hand-crafted log bundles, each with a known root cause and expected/anti keywords. used to spot-check whether a prompt change makes outputs better or worse before shipping.

**this is small enough to be honest about.**
- 50 cases gives a usable signal for a/b prompt comparison and regression. it is not a published-paper benchmark.
- keyword scoring rewards correct *vocabulary* in the answer, not correct *understanding*. addressed in a later pr by adding embedding-similarity scoring against gold-standard answers.
- anti-keywords catch obvious wrong directions but miss subtle errors.

## what it's actually good for

- comparing two prompt versions on the same dataset and seeing which scores higher (a/b).
- catching regressions when refactoring `llm.py`, `backend/prompts/*`, or the correlator.
- demonstrating that the project has an evaluation mindset, not just vibes.

## prompt versions

prompts live in `backend/prompts/v{N}.py` and are registered in `backend/prompts/__init__.py`. versions are append-only — never edit a published version, add a new one and switch via `PROMPT_VERSION` env var.

current versions:
- `v1` — original. `root_cause`, `next_step`, `evidence` fields.
- `v2` — adds `category` (db|auth|network|memory|config|upstream|cache|kafka|other) and `confidence` (high|medium|low). default since 0.5.
- `v3` — same fields as v2 but the model is required to return strict json (`response_format=json_object`). parsed fields land in dedicated columns and are scored by name in eval.

## run

```bash
# defaults to PROMPT_VERSION env var (v2)
python -m eval.run_eval                      # writes eval/results-v2.json
python -m eval.run_eval --version v1         # writes eval/results-v1.json
python -m eval.run_eval --case db_timeout    # one case
```

## a/b compare

```bash
python -m eval.run_eval --version v1
python -m eval.run_eval --version v2
python -m eval.compare eval/results-v1.json eval/results-v2.json
```

prints a per-case delta + aggregate side-by-side. arrows mark cases where one version scored at least 0.05 higher than the other.

## scoring

each case has a hand-written `gold` answer (1-2 sentences capturing the right root cause and action) and `expected_keywords` / `anti_keywords` for the legacy keyword scorer.

three modes (`--scorer`):
- `keyword` — legacy. `0.7*keyword_hit + 0.3*anti_clean`.
- `embedding` — `cosine(embed(analysis), embed(gold))` using azure openai `text-embedding-3-small`. embeddings are deterministic and cached to `eval/.embed_cache.json` so the gold answers are embedded once.
- `both` (default) — `0.5*keyword + 0.5*embedding`. catches both vocabulary and semantic mismatches.

a case is "passing" if `case_score >= 0.7`. embedding similarity is a stronger signal than keyword match but is not ground truth — it rewards answers that *sound* like the gold answer, not necessarily ones that are operationally correct.

## agreement (multi-seed runs)

```bash
python -m eval.run_eval --runs 3 --temperature 0.7
```

each case runs N times with seeds 1..N. per case we record:
- `agreement_pairwise_cos` — mean cosine similarity across all pairs of run embeddings.
- `agreement_category` — fraction of run pairs that picked the same `category`.

high pairwise cos with high category agreement = the model is consistent on this case under sampling.
high cos but low category agreement = the model wanders semantically while keeping the same vocabulary, or vice-versa.

cost: `--runs N` multiplies the llm bill by N. embeddings for identical run outputs hit the local cache so duplicate scoring is free.

## what's still missing (deliberate, not pretending)

- structured outputs scored against named fields (root_cause, category) instead of free text. v3 prompt already populates them; the scorer doesn't yet use them directly.
