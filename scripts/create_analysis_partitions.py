"""create monthly partitions for the analyses table going N months forward from a start date.

usage:
    python scripts/create_analysis_partitions.py --months 6
    python scripts/create_analysis_partitions.py --start 2027-06 --months 12

idempotent (uses 'create table if not exists'). run from cron monthly so partitions stay ahead
of incoming data; without it, new rows fall into analyses_default which is fine but defeats the
point of partitioning.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import db  # noqa: E402


def _month_after(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--start", help="YYYY-MM start month (default: today)")
    p.add_argument("--months", type=int, default=6, help="how many months forward (default 6)")
    args = p.parse_args()

    if args.start:
        y, m = (int(x) for x in args.start.split("-"))
    else:
        today = date.today()
        y, m = today.year, today.month

    db.init_pool()
    created: list[str] = []
    skipped: list[str] = []
    with db.conn() as c, c.cursor() as cur:
        for _ in range(args.months):
            ny, nm = _month_after(y, m)
            partition = f"analyses_y{y:04d}m{m:02d}"
            stmt = (
                f"create table if not exists {partition} partition of analyses "
                f"for values from ('{y:04d}-{m:02d}-01') to ('{ny:04d}-{nm:02d}-01')"
            )
            cur.execute(stmt)
            cur.execute(
                "select 1 from pg_class where relname = %s and relkind = 'r'",
                (partition,),
            )
            (created if cur.fetchone() else skipped).append(partition)
            y, m = ny, nm

    print(f"ensured {len(created)} partition(s):")
    for p_ in created:
        print(f"  {p_}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
