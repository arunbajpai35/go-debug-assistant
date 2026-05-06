from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta


def parse_ts(ts: str) -> datetime:
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def correlate(logs: Iterable[dict], window_seconds: int = 60) -> dict[str, list[dict]]:
    """group logs by trace_id, then expand each trace's window to neighbour logs within window_seconds."""
    parsed = []
    for entry in logs:
        if "trace_id" not in entry or "timestamp" not in entry:
            continue
        try:
            ts = parse_ts(entry["timestamp"])
        except ValueError:
            continue
        parsed.append({**entry, "_ts": ts})

    parsed.sort(key=lambda e: e["_ts"])

    by_trace: dict[str, list[dict]] = defaultdict(list)
    for e in parsed:
        by_trace[e["trace_id"]].append(e)

    out: dict[str, list[dict]] = {}
    delta = timedelta(seconds=window_seconds)
    for trace_id, trace_logs in by_trace.items():
        first = trace_logs[0]["_ts"] - delta
        last = trace_logs[-1]["_ts"] + delta
        bundle: list[dict] = []
        seen: set[int] = set()
        for e in parsed:
            if first <= e["_ts"] <= last:
                key = id(e)
                if key in seen:
                    continue
                seen.add(key)
                bundle.append(e)
        out[trace_id] = sorted(bundle, key=lambda e: e["_ts"])

    for v in out.values():
        for e in v:
            e.pop("_ts", None)
    return out


def format_window(logs: list[dict]) -> str:
    return "\n".join(f"[{e['timestamp']}] {e.get('level', '?')}: {e.get('message', '')}" for e in logs)
