"""compare two eval result files side-by-side.

usage:
    python -m eval.compare results-v1.json results-v2.json
"""
import argparse
import json
import sys
from pathlib import Path

DELTA_THRESHOLD = 0.05  # absolute delta below this is shown as no-change


def diff_results(a: dict, b: dict, threshold: float = DELTA_THRESHOLD) -> list[dict]:
    """returns a per-case row sorted by case id. each row carries the comparison data the
    cli prints; pulled out as a pure function so it's testable."""
    a_by_id = {c["id"]: c for c in a["cases"]}
    b_by_id = {c["id"]: c for c in b["cases"]}
    rows: list[dict] = []
    for case_id in sorted(a_by_id.keys() | b_by_id.keys()):
        sa = a_by_id.get(case_id, {}).get("case_score")
        sb = b_by_id.get(case_id, {}).get("case_score")
        if sa is None or sb is None:
            rows.append({"id": case_id, "a": sa, "b": sb, "delta": None, "marker": "?"})
            continue
        delta = sb - sa
        if delta > threshold:
            marker = "↑"
        elif delta < -threshold:
            marker = "↓"
        else:
            marker = " "
        rows.append({"id": case_id, "a": sa, "b": sb, "delta": delta, "marker": marker})
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("a", help="first results json (the baseline)")
    p.add_argument("b", help="second results json (the candidate)")
    args = p.parse_args()

    a = json.loads(Path(args.a).read_text())
    b = json.loads(Path(args.b).read_text())

    print(f"{'case':<28} {'a':>6} {'b':>6} {'Δ':>7}")
    print("-" * 50)
    for row in diff_results(a, b):
        if row["delta"] is None:
            print(f"{row['id']:<28} missing on one side")
            continue
        print(f"{row['id']:<28} {row['a']:>6.2f} {row['b']:>6.2f} {row['delta']:>+7.2f} {row['marker']}")

    print()
    print(f"aggregate a: {a['aggregate']}")
    print(f"aggregate b: {b['aggregate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
