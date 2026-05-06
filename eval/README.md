# eval

25 hand-crafted log bundles, each with a known root cause and expected/anti keywords. used to spot-check whether a prompt change makes outputs better or worse before shipping.

**this is not a benchmark and should not be cited as one.**
- 25 cases is small. it spots regressions, it does not measure accuracy.
- keyword scoring is brittle: it rewards correct *vocabulary* in the answer, not correct *understanding*.
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

```
keyword_hit  = expected_keywords matched in analysis (case-insensitive substring) / len(expected_keywords)
anti_clean   = anti_keywords absent in analysis / len(anti_keywords)
case_score   = 0.7 * keyword_hit + 0.3 * anti_clean
aggregate    = mean(case_score) across successful cases
```

a case is "passing" if `case_score >= 0.7`. look at per-case results, not just the aggregate.

## what's still missing (deliberate, not pretending)

- 50+ cases would let you make a real claim. 25 lets you spot regressions, not measure accuracy.
- structured outputs scored against named fields (root_cause, category) instead of free text.
- agreement metric across multiple llm runs (same case, same prompt, multiple seeds).
- gold-standard analyses written by a human, scored via embedding similarity instead of keyword match.
