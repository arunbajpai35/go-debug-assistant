# eval

10 hand-crafted log bundles, each with a known root cause and expected/anti keywords. used to spot-check whether a prompt change makes outputs better or worse before shipping.

**this is not a benchmark and should not be cited as one.**
- 10 cases is too small to claim accuracy. it's a smoke test.
- keyword scoring is brittle: it rewards correct *vocabulary* in the answer, not correct *understanding*.
- anti-keywords catch obvious wrong directions but miss subtle errors.

## what it's actually good for

- comparing two prompt versions on the same dataset and seeing which scores higher.
- catching regressions when refactoring `llm.py` or `prompts`.
- demonstrating that the project has an evaluation mindset, not just vibes.

## run

```bash
# requires real azure openai credentials in .env
python -m eval.run_eval
python -m eval.run_eval --case db_timeout
```

writes `eval/results.json` with per-case scores + aggregate.

## scoring

```
keyword_hit  = expected_keywords matched in analysis (case-insensitive substring) / len(expected_keywords)
anti_clean   = anti_keywords absent in analysis / len(anti_keywords)
case_score   = 0.7 * keyword_hit + 0.3 * anti_clean
aggregate    = mean(case_score) across successful cases
```

a case is "passing" if `case_score >= 0.7`. the aggregate number is a single coarse signal — look at per-case results to see what's actually failing.

## what's missing (deliberate, not pretending otherwise)

- larger labeled set (50+ cases needed for any real claim)
- structured outputs scored against fields (root_cause, suggested_action) not free text
- side-by-side prompt comparison report
- agreement metric across multiple llm runs (same case, same prompt, multiple seeds)
- gold-standard analyses written by a human, scored via embedding similarity instead of keyword match
