"""compare two eval result files side-by-side.

usage:
    python -m eval.compare results-v1.json results-v2.json
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("a", help="first results json (the baseline)")
    p.add_argument("b", help="second results json (the candidate)")
    args = p.parse_args()

    a = json.loads(Path(args.a).read_text())
    b = json.loads(Path(args.b).read_text())

    a_by_id = {c["id"]: c for c in a["cases"]}
    b_by_id = {c["id"]: c for c in b["cases"]}

    print(f"{'case':<28} {'a':>6} {'b':>6} {'Δ':>7}")
    print("-" * 50)
    for case_id in sorted(a_by_id.keys() | b_by_id.keys()):
        sa = a_by_id.get(case_id, {}).get("case_score")
        sb = b_by_id.get(case_id, {}).get("case_score")
        if sa is None or sb is None:
            print(f"{case_id:<28} missing on one side")
            continue
        delta = sb - sa
        marker = "↑" if delta > 0.05 else ("↓" if delta < -0.05 else " ")
        print(f"{case_id:<28} {sa:>6.2f} {sb:>6.2f} {delta:>+7.2f} {marker}")

    print()
    print(f"aggregate a: {a['aggregate']}")
    print(f"aggregate b: {b['aggregate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
