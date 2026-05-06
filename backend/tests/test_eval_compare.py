import pytest

from eval.compare import diff_results


def _payload(scores: dict[str, float]) -> dict:
    return {
        "aggregate": {"mean_score": sum(scores.values()) / max(len(scores), 1)},
        "cases": [{"id": cid, "case_score": s} for cid, s in scores.items()],
    }


def test_diff_results_marks_improvement_with_up_arrow():
    a = _payload({"db_timeout": 0.50})
    b = _payload({"db_timeout": 0.80})
    rows = diff_results(a, b)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "db_timeout"
    assert row["delta"] == pytest.approx(0.30)
    assert row["marker"] == "↑"


def test_diff_results_marks_regression_with_down_arrow():
    rows = diff_results(_payload({"x": 0.90}), _payload({"x": 0.40}))
    assert rows[0]["marker"] == "↓"


def test_diff_results_no_change_below_threshold():
    rows = diff_results(_payload({"x": 0.50}), _payload({"x": 0.53}))
    assert rows[0]["marker"] == " "


def test_diff_results_handles_one_sided_missing_cases():
    a = _payload({"only_a": 0.5})
    b = _payload({"only_b": 0.5})
    rows = diff_results(a, b)
    ids = {r["id"]: r for r in rows}
    assert ids["only_a"]["delta"] is None
    assert ids["only_a"]["marker"] == "?"
    assert ids["only_b"]["delta"] is None


def test_diff_results_sorted_by_case_id():
    rows = diff_results(_payload({"b_case": 0.5, "a_case": 0.5}), _payload({"b_case": 0.5, "a_case": 0.5}))
    assert [r["id"] for r in rows] == ["a_case", "b_case"]


def test_diff_results_threshold_is_configurable():
    a = _payload({"x": 0.50})
    b = _payload({"x": 0.53})
    # default threshold (0.05): 0.03 delta is below it
    assert diff_results(a, b)[0]["marker"] == " "
    # tighter threshold marks it as an improvement
    assert diff_results(a, b, threshold=0.01)[0]["marker"] == "↑"
