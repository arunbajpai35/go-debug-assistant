"""tests for the agreement metric in eval/run_eval.py — pure logic, no real embeddings."""
from eval.run_eval import pairwise_agreement


def test_pairwise_agreement_returns_none_for_single_run():
    out = pairwise_agreement(["only one"], ["db"], cache={})
    assert out["pairwise_cos"] is None
    assert out["category_agreement"] is None


def test_pairwise_agreement_perfect_when_all_identical():
    cache = {"the same": [1.0, 0.0]}
    out = pairwise_agreement(["the same", "the same", "the same"], ["db", "db", "db"], cache)
    assert out["pairwise_cos"] == 1.0
    assert out["category_agreement"] == 1.0


def test_pairwise_agreement_zero_when_all_orthogonal_and_categories_differ():
    cache = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
    out = pairwise_agreement(["a", "b"], ["db", "cache"], cache)
    assert out["pairwise_cos"] == 0.0
    assert out["category_agreement"] == 0.0


def test_pairwise_agreement_partial_category_agreement():
    cache = {"a": [1.0, 0.0], "b": [1.0, 0.0]}  # identical embeddings
    # 3 runs, categories: db, db, cache → pairs: (db,db)=match, (db,cache)=miss, (db,cache)=miss
    out = pairwise_agreement(["a", "a", "b"], ["db", "db", "cache"], cache)
    assert out["pairwise_cos"] == 1.0
    assert out["category_agreement"] == round(1 / 3, 3)


def test_pairwise_agreement_skips_pairs_with_empty_text():
    cache = {"a": [1.0, 0.0]}
    out = pairwise_agreement(["a", ""], ["db", None], cache)
    # one empty side → cosine pair skipped → no data → None
    assert out["pairwise_cos"] is None
    assert out["category_agreement"] is None
